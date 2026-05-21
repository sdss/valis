# encoding: utf-8
#
# test_auth.py — smoke tests for /auth endpoints

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from valis.main import app
from valis.settings import Settings, settings


@pytest.fixture(scope='module')
def client():
    yield TestClient(app)


def _mock_crowd_login(access='test_access', refresh='test_refresh'):
    """Return a mock that simulates a successful SDSS Crowd login response."""
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.is_error = False
    mock_resp.json.return_value = {'access': access, 'refresh': refresh}
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=mock_resp)
    return client


def _mock_crowd_refresh(access='new_access'):
    """Return a mock that simulates a successful SDSS Crowd refresh response."""
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.is_error = False
    mock_resp.json.return_value = {'access': access}
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=mock_resp)
    return client


def _mock_crowd_payload(payload):
    """Return a mock that simulates a successful SDSS Crowd JSON response."""
    mock_resp = AsyncMock(spec=httpx.Response)
    mock_resp.is_error = False
    mock_resp.json.return_value = payload
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=mock_resp)
    return client


class TestSettings:

    def test_app_auth_header_can_be_overridden(self):
        """Custom app auth header names are accepted and stripped."""
        local_settings = Settings(app_auth_header=' X-LVMVIS-Authorization ')
        assert local_settings.app_auth_header == 'X-LVMVIS-Authorization'

    @pytest.mark.parametrize('header_name', ['', 'X Bad Header', 'X-Test: Bearer token'])
    def test_app_auth_header_rejects_invalid_names(self, header_name):
        """Invalid header names must fail at startup config validation."""
        with pytest.raises(ValidationError):
            Settings(app_auth_header=header_name)


class TestLogin:

    def test_json_contract_preserved(self, client):
        """JSON body must still contain all three fields old clients expect."""
        mock_client = _mock_crowd_login()
        with patch('valis.routes.auth.httpx.AsyncClient', return_value=mock_client):
            resp = client.post('/auth/login', data={'username': 'u', 'password': 'p'})
        assert resp.status_code == 200
        data = resp.json()
        assert data['access_token'] == 'test_access'
        assert data['token_type'] == 'bearer'
        assert data['refresh_token'] == 'test_refresh'

    def test_set_cookie_present(self, client):
        """Login must set the HttpOnly refresh cookie."""
        mock_client = _mock_crowd_login()
        with patch('valis.routes.auth.httpx.AsyncClient', return_value=mock_client):
            resp = client.post('/auth/login', data={'username': 'u', 'password': 'p'})
        assert settings.cookie_name in resp.cookies


class TestRefresh:

    def test_refresh_via_authorization_header(self, client):
        """Old-client path: Authorization header is used, cookie ignored."""
        mock_client = _mock_crowd_refresh('header_access')
        with patch('valis.routes.auth.httpx.AsyncClient', return_value=mock_client):
            resp = client.post(
                '/auth/refresh',
                headers={'Authorization': 'Bearer test_refresh'},
            )
        assert resp.status_code == 200
        assert resp.json()['access_token'] == 'header_access'

    def test_refresh_via_cookie_fallback(self, client):
        """New-client path: cookie used when Authorization header is absent."""
        mock_client = _mock_crowd_refresh('cookie_access')
        client.cookies.set(settings.cookie_name, 'test_refresh')
        with patch('valis.routes.auth.httpx.AsyncClient', return_value=mock_client):
            resp = client.post('/auth/refresh')
        client.cookies.delete(settings.cookie_name)
        assert resp.status_code == 200
        assert resp.json()['access_token'] == 'cookie_access'

    def test_refresh_ignores_basic_authorization_and_uses_cookie(self, client):
        """External Basic auth must not override the HttpOnly refresh cookie."""
        mock_client = _mock_crowd_refresh('cookie_access')
        client.cookies.set(settings.cookie_name, 'test_refresh')
        with patch('valis.routes.auth.httpx.AsyncClient', return_value=mock_client):
            resp = client.post('/auth/refresh', headers={'Authorization': 'Basic external'})
        client.cookies.delete(settings.cookie_name)
        assert resp.status_code == 200
        assert resp.json()['access_token'] == 'cookie_access'
        mock_client.post.assert_awaited_once_with(
            'https://api.sdss.org/crowd/credential/refresh',
            headers={'Credential': 'Bearer test_refresh'},
        )

    def test_refresh_no_token_returns_401(self, client):
        """Missing both Authorization and cookie must return 401."""
        resp = client.post('/auth/refresh')
        assert resp.status_code == 401


class TestAppAuthHeader:

    def test_custom_header_has_priority_over_standard_authorization(self, client, monkeypatch):
        """Configured app auth header must win when proxy auth also exists."""
        monkeypatch.setattr(settings, 'app_auth_header', 'X-LVMVIS-Authorization')
        mock_client = _mock_crowd_payload({
            'member': {'username': 'u'},
        })
        with patch('valis.routes.auth.httpx.AsyncClient', return_value=mock_client):
            resp = client.post(
                '/auth/user',
                headers={
                    'Authorization': 'Basic external',
                    'X-LVMVIS-Authorization': 'Bearer app_access',
                },
            )
        assert resp.status_code == 200
        assert resp.json()['username'] == 'u'
        mock_client.post.assert_awaited_once_with(
            'https://api.sdss.org/crowd/credential/member',
            headers={'Credential': 'Bearer app_access'},
        )

    def test_standard_authorization_bearer_remains_fallback(self, client, monkeypatch):
        """Standard Bearer auth remains valid when the custom header is absent."""
        monkeypatch.setattr(settings, 'app_auth_header', 'X-LVMVIS-Authorization')
        mock_client = _mock_crowd_payload({'msg': 'ok', 'identity': 'u'})
        with patch('valis.routes.auth.httpx.AsyncClient', return_value=mock_client):
            resp = client.post('/auth/verify', headers={'Authorization': 'Bearer app_access'})
        assert resp.status_code == 200
        assert resp.json()['identity'] == 'u'
        mock_client.post.assert_awaited_once_with(
            'https://api.sdss.org/crowd/credential/identity',
            headers={'Credential': 'Bearer app_access'},
        )

    def test_basic_authorization_is_not_app_auth(self, client, monkeypatch):
        """Basic auth belongs to the upstream proxy, not the app auth layer."""
        monkeypatch.setattr(settings, 'app_auth_header', 'X-LVMVIS-Authorization')
        with patch('valis.routes.auth.httpx.AsyncClient') as mock_client:
            resp = client.post('/auth/user', headers={'Authorization': 'Basic external'})
        assert resp.status_code == 401
        mock_client.assert_not_called()


class TestLogout:

    def test_logout_clears_cookie(self, client):
        """Logout response must delete the refresh cookie (Max-Age=0 or expired)."""
        resp = client.post('/auth/logout')
        assert resp.status_code == 200
        assert resp.json() == {'msg': 'logged out'}
        # TestClient stores the cleared cookie; its value should be empty or absent
        assert client.cookies.get(settings.cookie_name, '') == ''
