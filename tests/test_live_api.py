"""Contract tests for external API integrations.

Run with: pytest -m live_api
These verify that the mock data in conftest.py still matches real API responses.
"""

import pytest

from pyked.orcid import search_orcid
from pyked.validation import crossref_api
from tests._mock_data import CROSSREF_RESPONSES as _CROSSREF_RESPONSES
from tests._mock_data import ORCID_RESPONSES as _ORCID_RESPONSES


@pytest.mark.live_api
class TestCrossrefContract:
    """Verify mock Crossref data matches live API responses."""

    @pytest.mark.parametrize("doi", list(_CROSSREF_RESPONSES.keys()))
    def test_doi_accessible(self, doi):
        """Ensure each mocked DOI is reachable via the real API."""
        result = crossref_api.works(ids=doi)
        assert "message" in result

    @pytest.mark.parametrize("doi", list(_CROSSREF_RESPONSES.keys()))
    def test_mock_matches_real_response(self, doi):
        """Ensure mock data fields match the real Crossref response."""
        real = crossref_api.works(ids=doi)["message"]
        mock = _CROSSREF_RESPONSES[doi]

        # journal title
        assert real["container-title"][0] == mock["container-title"][0], (
            f"container-title mismatch for {doi}: "
            f"real={real['container-title'][0]!r}, mock={mock['container-title'][0]!r}"
        )

        # year (prefer published-print, fall back to published-online like validation.py does)
        real_pub = real.get("published-print") or real.get("published-online", {})
        real_year = real_pub["date-parts"][0][0]
        mock_year = mock["published-print"]["date-parts"][0][0]
        assert (
            real_year == mock_year
        ), f"year mismatch for {doi}: real={real_year}, mock={mock_year}"

        # volume (optional)
        if "volume" in mock:
            assert str(real.get("volume", "")) == str(mock["volume"]), (
                f"volume mismatch for {doi}: "
                f"real={real.get('volume')!r}, mock={mock['volume']!r}"
            )

        # page (optional)
        if "page" in mock:
            assert real.get("page", "") == mock["page"], (
                f"page mismatch for {doi}: " f"real={real.get('page')!r}, mock={mock['page']!r}"
            )

        # author family names
        real_families = {a["family"] for a in real.get("author", [])}
        mock_families = {a["family"] for a in mock.get("author", [])}
        assert real_families == mock_families, (
            f"author family names mismatch for {doi}: "
            f"real={real_families}, mock={mock_families}"
        )


@pytest.mark.live_api
class TestOrcidContract:
    """Verify mock ORCID data matches live API responses."""

    @pytest.mark.parametrize("orcid", list(_ORCID_RESPONSES.keys()))
    def test_orcid_accessible(self, orcid):
        """Ensure each mocked ORCID is reachable via the real API."""
        result = search_orcid(orcid)
        assert "name" in result

    @pytest.mark.parametrize("orcid", list(_ORCID_RESPONSES.keys()))
    def test_mock_matches_real_response(self, orcid):
        """Ensure mock name fields match the real ORCID response."""
        real = search_orcid(orcid)
        mock = _ORCID_RESPONSES[orcid]

        real_family = real["name"]["family-name"]["value"]
        mock_family = mock["name"]["family-name"]["value"]
        assert (
            real_family == mock_family
        ), f"family-name mismatch for {orcid}: real={real_family!r}, mock={mock_family!r}"

        real_given = real["name"]["given-names"]["value"]
        mock_given = mock["name"]["given-names"]["value"]
        # Only check that the mock given name is a prefix/match of the real one
        # (mock may use "Kyle" while real has "Kyle E.")
        assert real_given.startswith(
            mock_given
        ), f"given-names mismatch for {orcid}: real={real_given!r}, mock={mock_given!r}"
