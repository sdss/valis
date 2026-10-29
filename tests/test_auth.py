from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from valis.routes import auth as auth_routes


@pytest.fixture
def auth_client(monkeypatch):
    """Fixture for mocking the auth client and crowd source"""
    state = {"status_code": 200, "requests": []}

    def handle_crowd_request(request):
        state["requests"].append((str(request.url), request.headers.get("Credential")))
        return httpx.Response(
            state["status_code"],
            json={"msg": "ok", "identity": "test-user"},
        )

    def mock_async_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handle_crowd_request)
        return httpx.AsyncClient(*args, **kwargs)

    monkeypatch.setattr(auth_routes, "httpx", SimpleNamespace(AsyncClient=mock_async_client))
    monkeypatch.setattr(auth_routes.settings, "env", "production")

    app = FastAPI()

    @app.get("/protected")
    async def protected(credentials: dict = Depends(auth_routes.set_auth)):
        return credentials

    with TestClient(app) as client:
        yield client, state


def test_protected_release_requires_token(auth_client):
    """test a protected route requires a token"""
    client, state = auth_client

    response = client.get("/protected?release=WORK")

    assert response.status_code == 401
    assert state["requests"] == []


def test_protected_release_verifies_token(auth_client):
    """test that a protected route verifies the token"""
    client, state = auth_client

    response = client.get(
        "/protected?release=WORK",
        headers={"Authorization": "Bearer valid-test-token"},
    )

    assert response.status_code == 200
    assert response.json() == {"token": "valid-test-token", "release": "WORK"}
    assert state["requests"] == [
        (
            "https://api.sdss.org/crowd/credential/identity",
            "Bearer valid-test-token",
        )
    ]


def test_protected_release_rejects_token(auth_client):
    """test we reject an invalid token"""
    client, state = auth_client
    state["status_code"] = 401

    response = client.get(
        "/protected?release=WORK",
        headers={"Authorization": "Bearer invalid-test-token"},
    )

    assert response.status_code == 401
    assert len(state["requests"]) == 1


def test_public_release_does_not_require_token(auth_client):
    """test that a public release does not require a token"""
    client, state = auth_client

    response = client.get("/protected?release=DR17")

    assert response.status_code == 200
    assert response.json() == {"token": None, "release": "DR17"}
    assert state["requests"] == []


def test_unrecognized_release_does_not_bypass_validation(auth_client):
    """test that an unrecognized DR release does not bypass release validation"""
    client, state = auth_client

    response = client.get("/protected?release=DR99")

    assert response.status_code == 422
    assert state["requests"] == []


def test_dev_environment_does_not_require_token(auth_client, monkeypatch):
    """test that in the development environment, a token is not required"""
    client, state = auth_client
    monkeypatch.setattr(auth_routes.settings, "env", "development")

    response = client.get("/protected?release=WORK")

    assert response.status_code == 200
    assert response.json() == {"token": None, "release": "WORK"}
    assert state["requests"] == []
