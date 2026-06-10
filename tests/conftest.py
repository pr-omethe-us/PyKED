"""Shared test fixtures."""

from unittest.mock import patch

import pytest

_CROSSREF_RESPONSES = {
    "10.1016/j.ijhydene.2007.04.008": {
        "container-title": ["International Journal of Hydrogen Energy"],
        "published-print": {"date-parts": [[2007]]},
        "volume": "32",
        "page": "2216-2226",
        "author": [
            {"given": "N.", "family": "Chaumeix"},
            {"given": "S.", "family": "Pichon"},
            {"given": "F.", "family": "Lafosse"},
            {"given": "C.-E.", "family": "Paillard"},
        ],
    },
    "10.1002/kin.20180": {
        "container-title": ["International Journal of Chemical Kinetics"],
        "published-print": {"date-parts": [[2006]]},
        "volume": "38",
        "page": "516-529",
        "author": [
            {"given": "Gaurav", "family": "Mittal"},
            {
                "given": "Chih-Jen",
                "family": "Sung",
                "ORCID": "http://orcid.org/0000-0003-2046-8076",
            },
            {"given": "Richard A.", "family": "Yetter"},
        ],
    },
    # No "volume" or "page" — tested by test_no_volume_in_DOI
    "10.1115/GT2013-94282": {
        "container-title": ["Volume 1A: Combustion, Fuels and Emissions"],
        "published-print": {"date-parts": [[2013]]},
        "author": [
            {"given": "F.", "family": "Xu"},
            {"given": "V.", "family": "Nori"},
            {"given": "J.", "family": "Basani"},
        ],
    },
    "10.1016/j.combustflame.2011.08.014": {
        "container-title": ["Combustion and Flame"],
        "published-print": {"date-parts": [[2012]]},
        "volume": "159",
        "page": "516-527",
        "author": [
            {"given": "Ivo", "family": "Stranic"},
            {"given": "Deanna P.", "family": "Chase"},
            {"given": "Joseph T.", "family": "Harmon"},
            {"given": "Sheng", "family": "Yang"},
            {"given": "David F.", "family": "Davidson"},
            {"given": "Ronald K.", "family": "Hanson"},
        ],
    },
}


def _mock_works(ids=None, **kwargs):
    if ids in _CROSSREF_RESPONSES:
        return {"message": _CROSSREF_RESPONSES[ids]}
    raise KeyError(
        f"DOI {ids!r} not in mock data; add it to _CROSSREF_RESPONSES in tests/conftest.py"
    )


@pytest.fixture
def mock_crossref_api():
    with patch("pyked.validation.crossref_api.works", side_effect=_mock_works):
        yield
