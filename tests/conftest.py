"""Shared test fixtures."""

from unittest.mock import MagicMock, patch

import habanero
import httpx
import pytest

from tests._mock_data import CROSSREF_INVALID_DOIS, CROSSREF_RESPONSES, ORCID_RESPONSES


def _mock_works(ids=None, **kwargs):
    if ids in CROSSREF_INVALID_DOIS:
        raise habanero.RequestError(404, "Not Found")
    if ids in CROSSREF_RESPONSES:
        return {"message": CROSSREF_RESPONSES[ids]}
    raise KeyError(
        f"DOI {ids!r} not in mock data; add it to CROSSREF_RESPONSES in tests/_mock_data.py"
    )


def _mock_search_orcid(orcid):
    if orcid in ORCID_RESPONSES:
        return ORCID_RESPONSES[orcid]
    raise httpx.HTTPStatusError(
        "404 Not Found",
        request=MagicMock(spec=httpx.Request),
        response=MagicMock(spec=httpx.Response),
    )


@pytest.fixture
def mock_crossref_api():
    with patch("pyked.validation.crossref_api.works", side_effect=_mock_works):
        yield


@pytest.fixture
def mock_orcid_api():
    with patch("pyked.validation.search_orcid", side_effect=_mock_search_orcid):
        yield


@pytest.fixture
def mock_all_apis(mock_crossref_api, mock_orcid_api):
    """Activates both Crossref and ORCID API mocks."""
    yield
