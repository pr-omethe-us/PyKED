.. Development documentation

Development
===========

This page covers how to set up a development environment and run the test suite when
contributing to PyKED.

Installing for development
--------------------------

Clone the repository and install in editable mode with all developer dependencies::

    git clone https://github.com/pr-omethe-us/PyKED
    cd PyKED
    pip install -e . --group all

Running the tests
-----------------

PyKED uses a two-tier test structure: a fast, fully-mocked default suite and a separate set of
live API contract tests that verify the mocks stay accurate.

Default suite
~~~~~~~~~~~~~

All tests in the default suite use mock responses for the Crossref and ORCID external APIs, so
they run offline and at full speed::

    pytest                   # run all tests
    pytest --cov=pyked       # with coverage report
    pytest -v                # verbose output

Live API contract tests
~~~~~~~~~~~~~~~~~~~~~~~

A separate set of tests marked ``live_api`` call the real Crossref and ORCID APIs to confirm
that the mock data in ``tests/_mock_data.py`` still matches actual responses. These are excluded
from the default run and from the CI checks on pull requests, so run them by hand before
submitting a pull request, whatever it changes: they are there to catch errors you did not
expect::

    pytest -m live_api -v

You can also narrow the scope::

    pytest -m live_api -v -k "Crossref"   # Crossref contract tests only
    pytest -m live_api -v -k "Orcid"      # ORCID contract tests only

These contract tests run automatically every Monday at 06:00 UTC via GitHub Actions. If the
weekly run fails, the mock data likely needs updating — compare the failure output against the
entries in ``tests/_mock_data.py`` and update as needed.

Adding new API-dependent tests
-------------------------------

If you add a test that loads a ChemKED file with a DOI or author ORCID, the validation layer
will call the Crossref and/or ORCID APIs. Rather than hitting the real APIs, extend the mocks:

1. Add your DOI's expected response to ``CROSSREF_RESPONSES`` in ``tests/_mock_data.py``, with
   the fields copied from the real CrossRef record. If the test needs a record that does not
   exist, such as one with made-up text, add it to ``CROSSREF_SYNTHETIC_RESPONSES`` instead.
2. Add any ORCID identifiers to ``ORCID_RESPONSES`` in the same file.
3. Apply the appropriate fixture to your test:

   - ``mock_crossref_api`` — patches Crossref only
   - ``mock_orcid_api`` — patches ORCID only
   - ``mock_all_apis`` — patches both (preferred for most cases)

Example::

    def test_my_new_feature(self, mock_all_apis):
        c = ChemKED(yaml_file="tests/my_new_file.yaml")
        assert c.reference.doi == "10.xxxx/my.doi"

The real records are also what the live contract tests compare against, so adding the entry to
``CROSSREF_RESPONSES`` keeps both the unit test mocks and the contract tests correct. The
contract tests do not check ``CROSSREF_SYNTHETIC_RESPONSES``, since its DOIs do not exist and
CrossRef would not find them.
