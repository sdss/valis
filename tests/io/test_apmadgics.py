import h5py
import numpy as np
import pytest
from astropy.io import fits

from valis.io import apmadgics


@pytest.fixture
def visit_factory(tmp_path):
    """Fixture factory to create a visit file"""
    visits = {
        "sdss_id": np.array([55750505, 55750505, 55499273], dtype=np.int32),
        "map2madgics": np.array([1, 2, 3], dtype=np.int32),
        "mjd": np.array([58295, 58731, 58384], dtype=np.int32),
        "plate": np.array([9135, 7950, 7950], dtype=np.int32),
        "fiberid": np.array([300, 300, 301], dtype=np.int32),
        "field": np.array(["N188", "N188", "N188"], dtype=str),
        "telescope": np.array(["apo25m"] * 3),
        "apogee_id": np.array(["2M00000000+0000000"] * 3),
        "gaiaedr3_source_id": np.array([1001, 1002, 2001], dtype=np.int64),
        "cartVisit": np.array([1, 2, 3], dtype=np.int32),
        "ra": np.array([7.754378, 7.754378, 8.754378]),
        "dec": np.array([86.036034, 86.036034, 56.036034]),
        "glon": np.array([122.54853643911692, 122.54853643911692, 222.54853643911692]),
        "glat": np.array([23.179648694299992, 23.179648694299992, 33.179648694299992]),
        "rv_bary": np.array([-12.510700051155107, -12.343094224709967, -12.370256644397399], dtype=np.float32),
        "rv_flag": np.array([0, 1, 0], dtype=np.int32),
        "rv_verr_sys": np.array([0.1, 0.2, 0.3], dtype=np.float32),
    }
    formats = {
        "telescope": "10A",
        "apogee_id": "20A",
        "field": "10A",
        "gaiaedr3_source_id": "K",
        "ra": "D",
        "dec": "D",
        "glon": "D",
        "glat": "D",
        "rv_bary": "E",
        "rv_verr_sys": "E",
    }

    def create_visit_file(star_prior):
        rv_offset = 10 if star_prior == "th" else 0
        columns = [
            fits.Column(
                name=name,
                format=formats.get(name, "J"),
                array=values + rv_offset if name == "rv_bary" else values,
            )
            for name, values in visits.items()
        ]
        visit_path = tmp_path / f"allvisit-{star_prior}.fits"
        fits.BinTableHDU.from_columns(columns).writeto(visit_path)
        return str(visit_path)

    return create_visit_file


@pytest.fixture
def dd_visit(visit_factory):
    """fixture to create the dd visit file"""
    return visit_factory("dd")


@pytest.fixture
def th_visit(visit_factory):
    """fixture to create the th visit file"""
    return visit_factory("th")


@pytest.fixture
def spectra_file(tmp_path):
    """Fixture to create the hdf5 spectra file"""
    spectra = np.arange(3 * 8700, dtype=np.float32).reshape(3, 8700)
    spectrum_path = tmp_path / "spectra.h5"
    with h5py.File(spectrum_path, "w") as hdf5_file:
        hdf5_file.create_dataset("apVisit_v0", data=spectra)
    return {"path": str(spectrum_path), "spectra": spectra}


@pytest.fixture
def mock_apmadgics_paths(monkeypatch, dd_visit, th_visit, spectra_file):
    paths = {
        ("allVisit_MADGICS", "dd"): dd_visit,
        ("allVisit_MADGICS", "th"): th_visit,
        ("apMADGICS_out_apVisit_v0", "dd"): spectra_file["path"],
    }
    def fake_build_file_path(values, product, _release):
        return paths.get((product, values["star_prior_type"]), "")

    monkeypatch.setattr(apmadgics, "build_file_path", fake_build_file_path)
    apmadgics.get_merged_allvisit.cache_clear()
    yield paths
    apmadgics.get_merged_allvisit.cache_clear()


@pytest.mark.usefixtures("mock_apmadgics_paths")
def test_allvisit_path(dd_visit):
    """test we get a path"""
    path = apmadgics._allvisit_path("dd", "vtest", "DR19")
    assert path == dd_visit


def test_allvisit_missing_file(monkeypatch):
    """test path not found"""
    monkeypatch.setattr(apmadgics, "build_file_path", lambda *args, **kwargs: "")
    with pytest.raises(FileNotFoundError, match="allVisit_apMADGICS file (.*?) could not be found"):
        apmadgics._allvisit_path("dd", "vtest", "DR19")


def test_read_columns(dd_visit):
    """test we can read columns"""
    columns = apmadgics._read_columns(dd_visit, select=lambda name: name.startswith("rv_"))

    assert set(columns) == {"rv_bary", "rv_flag", "rv_verr_sys"}
    assert columns["rv_bary"].tolist() == pytest.approx(
        [-12.510700051155107, -12.343094224709967, -12.370256644397399]
    )
    assert all(column.dtype.isnative for column in columns.values())


@pytest.mark.usefixtures("mock_apmadgics_paths")
def test_get_merged_allvisit():
    """test we get a merged allvisit file with dd/th columns"""
    table = apmadgics.get_merged_allvisit(vers="vtest", release="DR19")

    assert table["sdss_id"].tolist() == [55750505, 55750505, 55499273]
    assert table["rv_bary_dd"].tolist() == pytest.approx(
        [-12.510700051155107, -12.343094224709967, -12.370256644397399]
    )
    assert table["rv_bary_th"].tolist() == pytest.approx(
        [-2.510700051155107, -2.343094224709967, -2.370256644397399]
    )
    assert "rv_verr_sys_th" in table.colnames
    assert "rv_verr_sys" not in table.colnames


@pytest.mark.usefixtures("mock_apmadgics_paths")
def test_get_rows():
    """test we can get apmadgic rows for an sdss_id"""
    rows = apmadgics.get_madgic_rows(55750505, vers="vtest", release="DR19")

    assert len(rows) == 2
    assert rows["mjd"].tolist() == [58295, 58731]

    with pytest.raises(ValueError, match="SDSS ID 999 not found"):
        apmadgics.get_madgic_rows(999, vers="vtest", release="DR19")


def test_get_wavelength():
    """test we can get the apmadgic wavelength array"""
    wavelength = apmadgics.get_madgic_wavelength()

    assert wavelength.shape == (8700,)
    assert wavelength[0] == pytest.approx(15074.74588598709)
    assert np.all(np.diff(wavelength) > 0)


@pytest.mark.parametrize(
    ("sdss_id", "criteria", "expected_index"),
    [
        (55750505, {"mjd": 58731}, 2),
        (55499273, {}, 3),
    ],
)
@pytest.mark.usefixtures("mock_apmadgics_paths")
def test_get_index(sdss_id, criteria, expected_index):
    index = apmadgics.get_madgic_index(
        sdss_id,
        vers="vtest",
        release="DR19",
        **criteria,
    )

    assert index == expected_index


@pytest.mark.usefixtures("mock_apmadgics_paths")
def test_get_spectrum(spectra_file):
    spectrum = apmadgics.get_madgic_spectrum(
        sdss_id=55750505,
        mjd=58731,
        vers="vtest",
        release="DR19",
    )

    assert np.array_equal(spectrum["flux"], spectra_file["spectra"][1])
    assert spectrum["wavelength"].shape == (8700,)
    assert spectrum["unit_wavelength"] == "Angstrom"
    assert spectrum["unit_flux"] == "1e-17 erg / (Angstrom cm2 s)"


def test_missing_spectrum(monkeypatch):
    """test we when spectral file is missing"""
    monkeypatch.setattr(apmadgics, "build_file_path", lambda *args, **kwargs: "")

    with pytest.raises(FileNotFoundError, match="apMADGICS_out_apVisit_v0 (.*?) could not be found"):
        apmadgics.get_madgic_spectrum(sdss_id=55750505)