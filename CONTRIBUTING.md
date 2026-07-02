# Contributing

We welcome contributions in the form of bug reports, bug fixes, improvements to the documentation, ideas for enhancements, or the enhancements themselves!

You can find a [list of current issues](https://github.com/pr-omethe-us/PyKED/issues) in the project's GitHub repository. Feel free to tackle any existing bugs or enhancement ideas by submitting a [pull request](https://github.com/pr-omethe-us/PyKED/pulls). Some issues are marked as `beginner-friendly`. These issues are a great place to start working with PyKED and ChemKED, if you're new here.

## Bug Reports

 * Please include a short (but detailed) Python snippet or explanation for reproducing the problem. Attach or include a link to any input files that will be needed to reproduce the error.
 * Explain the behavior you expected, and how what you got differed.
 * Include the full text of any error messages that are printed on the screen.

## Pull Requests

 * If you're unfamiliar with Pull Requests, please take a look at the [GitHub documentation for them](https://help.github.com/articles/proposing-changes-to-a-project-with-pull-requests/).
 * **Make sure the test suite passes** on your computer, and that test coverage doesn't go down. To do this, run `pytest --cov=pyked` from the top-level directory. See [Testing](#testing) below for more detail.
 * *Always* add tests and docs for your code.
 * The use of emoji in Pull Requests is encouraged with the format ":emoji: Commit summary". See [this list of suggested emoji.](https://github.com/slashsBin/styleguide-git-commit-message#suggested-emojis)
 * Please reference relevant GitHub issues in your commit messages using `GH123` or `#123`.
 * Changes should be [PEP8](https://www.python.org/dev/peps/pep-0008/) and [PEP257](https://www.python.org/dev/peps/pep-0257/) compatible.
 * Keep style fixes to a separate commit to make your pull request more readable.
 * Add your changes into the [`CHANGELOG`](https://github.com/pr-omethe-us/PyKED/blob/main/CHANGELOG.md)
 * Docstrings are required and should follow the [Google style](http://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html).
 * When you start working on a pull request, start by creating a new branch pointing at the latest commit on [GitHub main](https://github.com/pr-omethe-us/PyKED/tree/main).
 * The copyright policy is detailed in the [`LICENSE`](https://github.com/pr-omethe-us/PyKED/blob/main/LICENSE).

## Testing

PyKED uses a two-tier test structure to keep the default suite fast and reliable while still
verifying that external API integrations stay accurate.

### Default test suite

All tests run by default use mocked external APIs (Crossref and ORCID). To run the full default
suite:

```bash
pytest                  # run all tests
pytest --cov=pyked      # with coverage
pytest -v               # verbose output
```

If you add a test that calls the Crossref or ORCID API, **do not hit the real API**. Instead:

1. Add your DOI to `CROSSREF_RESPONSES` in [`tests/_mock_data.py`](tests/_mock_data.py).
2. Add any ORCID identifiers to `ORCID_RESPONSES` in the same file.
3. Use the `mock_crossref_api`, `mock_orcid_api`, or `mock_all_apis` fixture from
   [`tests/conftest.py`](tests/conftest.py) in your test.

### Live API contract tests

A separate set of tests marked `live_api` calls the real Crossref and ORCID APIs to verify that
the mock data in `tests/_mock_data.py` still matches live responses. These are excluded from the
default run but can be triggered manually:

```bash
pytest -m live_api -v
```

These contract tests run automatically every Monday at 06:00 UTC via GitHub Actions
(`.github/workflows/live-api.yml`). If the weekly run fails, the mock data likely needs updating.

## Meta

Thanks to the useful [contributing guide of pyrk](https://github.com/pyrk/pyrk/blob/main/CONTRIBUTING.md), which served as an inspiration and starting point for this guide.
