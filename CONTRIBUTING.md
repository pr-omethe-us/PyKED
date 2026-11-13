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

## Making a release

These steps are for maintainers. A release has two outward steps that cannot be undone: pushing
a version tag publishes the package to PyPI, which never accepts the same version number twice,
and publishing a GitHub release makes Zenodo archive that version and mint its DOI. So finish
each step, and check that it worked, before starting the next. The commands below call the
`pr-omethe-us/PyKED` remote `upstream`.

PyKED follows [Semantic Versioning](https://semver.org/). Before 1.0, a release with breaking
changes or new features increases the minor version (for example, 0.5.0 to 0.6.0), and one with
only bug fixes increases the patch version (0.6.0 to 0.6.1).

### 1. Prepare the release commit

On a branch from the latest `main`, update:

* `src/pyked/_version.py`: set `__version__` to the new version.
* `src/pyked/schemas/chemked_schema.yaml`: add the new version to the `allowed` values of
  `chemked-version`. The converters write the current version into every file they produce, and
  a test fails if it is missing from this list.
* `CHANGELOG.md`: rename `## [Unreleased]` to `## [X.Y.Z] - YYYY-MM-DD`, add a new, empty
  `## [Unreleased]` section above it, and update the links at the bottom of the file:
  `[Unreleased]` now compares `vX.Y.Z...HEAD`, and a new `[X.Y.Z]` link compares the previous tag
  with `vX.Y.Z`.
* `CITATION.cff`: set `version` and `date-released`. Zenodo takes the metadata of the archived
  version from this file, so it must be right in the tagged commit.
* `CITATION.md`: update the version and year in the citation and in the BibTeX entry. The new
  version has no DOI until Zenodo mints it, so the DOI is updated in step 4.
* `LICENSE`: update the copyright year, if it has changed.

Then check the release locally:

```bash
pip install build twine cffconvert
pytest                                  # the default test suite
python -m build                         # build the sdist and wheel into dist/
twine check dist/*                      # check the package metadata PyPI will show
cffconvert --validate -i CITATION.cff   # check the citation metadata Zenodo will use
```

Merge the release commit into `main` through a pull request, and wait for CI to pass on `main`.

### 2. Tag the release and publish to PyPI

Tag the release commit on `main` with an annotated tag, and push only that tag:

```bash
git switch main
git pull upstream main
git tag -a vX.Y.Z -m "PyKED vX.Y.Z"
git push upstream vX.Y.Z
```

Pushing a tag that starts with `v` runs the `Publish to PyPI` workflow
(`.github/workflows/publish.yml`). It builds the package and uploads it to PyPI by trusted
publishing, through the `pypi` deployment environment, which accepts only the `main` branch and
`v*` tags, so no PyPI token is stored in the repository. Follow the run on the repository's
Actions tab, then check that <https://pypi.org/project/pyked/> shows the new version.

If the workflow fails before uploading, fix the problem on `main`, delete the tag, and tag the
fixed commit again:

```bash
git push upstream :refs/tags/vX.Y.Z
git tag -d vX.Y.Z
```

If a broken package was uploaded, it cannot be replaced: yank it on PyPI and release the next
patch version instead.

### 3. Create the GitHub release

Only once the package is on PyPI, create a GitHub release from the tag, with the new version's
section of `CHANGELOG.md` as its notes:

```bash
awk -v v="X.Y.Z" '$0 ~ "^## \\[" v "\\]" {f=1; next} /^## \[/ {f=0} f' CHANGELOG.md > notes.md
gh release create vX.Y.Z --repo pr-omethe-us/PyKED --verify-tag --title "vX.Y.Z" --notes-file notes.md
```

Alternatively, use **Releases > Draft a new release** on GitHub and choose the existing tag.
Publishing the release makes Zenodo archive the tagged source and mint a DOI for this version.
Processing can take a while. The concept DOI,
[10.5281/zenodo.597935](https://doi.org/10.5281/zenodo.597935), always resolves to the latest
version, and the new version is listed among its versions on Zenodo once it is archived. If
Zenodo reports an error, it is shown for the release on Zenodo's GitHub page.

### 4. Record the new DOI

Update `CITATION.md` with the DOI of the new version: in the citation, in the `doi` field of the
BibTeX entry, and in the list of version DOIs. Commit it to `main`.

The documentation site is rebuilt from `main` on every push, so it needs no separate step.

## Meta

Thanks to the useful [contributing guide of pyrk](https://github.com/pyrk/pyrk/blob/main/CONTRIBUTING.md), which served as an inspiration and starting point for this guide.
