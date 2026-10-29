# encoding: utf-8
#

import pathlib

import pytest
from fastapi import HTTPException

from valis.routes.access import Path, PathModel
from valis.routes.files import bytes_to_numpy, get_filepath


def get_data(response):
    assert response.status_code == 200
    return response.json()


def test_files(client):
    response = client.get("/file")
    data = get_data(response)
    assert "this route is for files" in data["info"]


def test_path(client, testfile):
    response = client.get("/paths/")
    data = get_data(response)
    assert "test" in data["names"]


def test_path_kwargs(client, testfile):
    response = client.get("/paths/keywords/test")
    data = get_data(response)
    assert data["name"] == "test"
    assert set(data["kwargs"]) == {"ver", "id"}


def test_file_info(client, testfile):
    response = client.get("/file/test/info", params={"release": "DR17", "kwargs": ["ver=v1", "id=A"]})
    data = get_data(response)
    assert "info" in data
    assert "Filename:" in data["info"][0]
    assert "dr17/test/spectro/redux/v1/testfile_A.fits" in data["info"][0]
    assert data["info"][3] == "  1  FLUX          1 ImageHDU         8   (5, 5)   float64   "


@pytest.mark.parametrize(
    "ext, exp",
    [
        (0, {"FILENAME": "testfile_A.fits", "TESTVER": "0.1.0"}),
        (1, {"EXTNAME": "FLUX", "NAXIS1": 5}),
        (2, {"EXTNAME": "PARAMS", "NAXIS1": 26}),
    ],
    ids=["primary", "image", "table"],
)
def test_file_header(client, testfile, ext, exp):
    response = client.get("/file/test/header", params={"release": "DR17", "kwargs": ["ver=v1", "id=A"], "ext": ext})
    data = get_data(response)

    hdr = data["header"]
    assert exp.items() <= hdr.items()


expdata = {
    0: None,
    1: [3.03865e-319, 3.03865e-319, 3.03865e-319, 3.03865e-319, 3.03865e-319],
    2: {
        "object": [
            "a",
            "b",
            "c",
        ],
        "flag": [0, 1, 2],
    },
}


@pytest.mark.parametrize("ext", [0, 1, 2], ids=["primary", "image", "table"])
def test_file_data(client, testfile, ext):
    response = client.get(
        "/file/test/data", params={"release": "DR17", "kwargs": ["ver=v1", "id=A"], "ext": ext, "header": False}
    )
    res = get_data(response)
    data = res["data"]
    exp = expdata[ext]

    if ext == 0:
        assert data is exp
    elif ext == 1:
        assert data[0] == exp
    elif ext == 2:
        assert exp.items() <= data.items()


@pytest.mark.parametrize("format", ["json", "csv", "bytes"])
def test_file_stream(client, testfile, format):
    response = client.get(
        "/file/test/stream", params={"release": "DR17", "kwargs": ["ver=v1", "id=A"], "ext": 1, "format": format}
    )
    assert response.status_code == 200
    if format == "json":
        data = response.json()
        assert data[0] == [3.03865e-319, 3.03865e-319, 3.03865e-319, 3.03865e-319, 3.03865e-319]
    elif format == "csv":
        data = response.content
        assert (
            "1.0000000000000000,1.0000000000000000,1.0000000000000000,1.0000000000000000,1.0000000000000000\n"
            in data.decode("utf-8")
        )
    elif format == "bytes":
        data = response.content
        assert data.startswith(b">f8|5,5|?\xf0\x00")
        arr = bytes_to_numpy(data)
        assert arr.shape == (5, 5)
        assert all(arr[0] == [1.0, 1.0, 1.0, 1.0, 1.0])


@pytest.fixture()
def model(setup_sas):
    """Fixture for creating a PathModel instance"""
    kk = {"mjd": "60448", "run2d": "v6_2_1", "catalogid": "27021603186436291", "fieldid": "110580"}
    p = Path(release="DR20")
    return PathModel(name="specLite", kwargs=kk, _path=p)


@pytest.mark.asyncio
async def test_get_filepath(model):
    """test getting a valid filepath"""
    pp = pathlib.Path(model.full)
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.touch()

    target = await get_filepath("specLite", model)
    assert pathlib.Path(target).is_file()


@pytest.mark.asyncio
async def test_get_filepath_no_file(model):
    """test no file found"""
    with pytest.raises(HTTPException, match="File not found"):
        await get_filepath("specLite", model)


@pytest.mark.asyncio
async def test_get_filepath_unsupported(model):
    """test unsupported file type"""
    model.full = model.full.replace("fits", "parquet")
    pp = pathlib.Path(model.full)
    pp.parent.mkdir(parents=True, exist_ok=True)
    pp.touch()

    with pytest.raises(HTTPException, match="Unsupported file type"):
        await get_filepath("specLite", model)


@pytest.mark.asyncio
async def test_get_filepath_incomplete(model):
    """Test incomplete path model"""
    model.full = None
    with pytest.raises(HTTPException, match="Incomplete file parameters"):
        await get_filepath("specLite", model)


@pytest.mark.asyncio
async def test_get_filepath_bad(model):
    """test a bad formatted filename"""
    model.full = f"$BOSS_DRP_DIR/{model.file}"
    with pytest.raises(HTTPException, match="Path contains unresolved environment variable"):
        await get_filepath("specLite", model)
