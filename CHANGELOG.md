# Change Log
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased]
### Added
- ReSpecTh 2.x support in `ReSpecTh_to_ChemKED`: the reference is read from the `bibliographyLink` child elements (`referenceDOI`, `details`) with no DOI lookup, falling back to the 1.x `doi` and `preferredKey` attributes
- Conversion of laminar burning velocity and speciation measurements, alongside ignition delay. ReSpecTh's four speciation experiment types all map to ChemKED `speciation measurement`
- Mapping tables in `converters.py` for ReSpecTh experiment types, apparatus kinds and modes, common property names, speciation independent variables, and ignition targets and types
- `apparatus_kind` argument to `ReSpecTh_to_ChemKED` and `-ak/--apparatus-kind` to `respth2ck`, for files whose apparatus ReSpecTh records only as the generic `flame`
- `uncertainty` and `evaluated standard deviation` properties and dataGroup columns are converted and attached to the quantity they describe, whether that is a datapoint value, a common property, a species amount, or a concentration profile
- ReSpecTh `comment` elements are converted to ChemKED `comments`
- `isvalid_experiment` validation rule cross-checking `experiment-type` against the datapoint contents and the apparatus kind, which the `anyof` datapoints schema cannot do on its own
- Round-trip tests asserting the converter reproduces each checked-in ReSpecTh/ChemKED fixture pair
- `resolve_reference` maps an uncertainty that points at a column by its `label` or `id`, and one that references `initial composition`, onto the quantity it describes; both were silently dropped before
- `0.5.0` added to the allowed `chemked-version` values, and a test asserting the current `__version__` is always among them, since `get_file_metadata` stamps it into every converted file

### Changed
- The `tubular reactor` apparatus kind is renamed `flow reactor`, the name ReSpecTh, the ChemKED database, and the speciation literature all use. `tubular reactor` is still accepted as converter input and maps to `flow reactor`
- The mole and mass fraction sum check uses a relative tolerance of 1e-3 (`composition_sum_tolerance`) rather than the NumPy default of 1e-5, so compositions reported to a few digits are not rejected for round-off
- An auxiliary profile against a `residence-time` axis is recorded with the axis name `time`, which `auxiliary-profiles.independent.name` allows, since a residence time is a time coordinate

### Fixed
- A composition amount of exactly zero, meaning a species measured as absent, is accepted when it carries uncertainty metadata. It was accepted without metadata and rejected with it, and `isvalid_composition` already allowed it. Only a negative value is an error for a property with no configured units
- The unsupported-composition-units error lists the units the converter actually accepts, built from `composition_units` rather than hand-written, so it cannot fall behind the table again
- Every text file is now opened with an explicit UTF-8 encoding. Reading or writing a ChemKED or ReSpecTh file whose author names contain non-ASCII characters previously depended on the platform's preferred encoding, and failed on Windows. `convert_to_ReSpecTh` could also rewrite its pretty-printed XML in the platform encoding while declaring UTF-8 in the file. The ruff rule `PLW1514` now enforces this
- Relative uncertainties and relative evaluated standard deviations are now checked to be dimensionless. They previously bypassed unit validation entirely, so `uncertainty-type: relative` with `uncertainty: 0.1 kelvin` validated and was then misread at load time
- An uncertainty value Pint cannot parse is reported as a validation error instead of raising `UndefinedUnitError` out of the validator
- Unit strings that ReSpecTh writes with bare negative exponents, such as `ms-1` and `kg m-2 s-1`, are normalized for Pint instead of escaping as a `DimensionalityError` from outside the guarded block
- `get_ignition_type` accepted only 5 of the 10 ignition types and 6 of the 18 ignition targets the schema allows; the vocabulary is now in step with `ignition_delay_schema.yaml` and is checked by a test
- `experimentType` is matched case-insensitively, so the lowercase spelling used throughout ReSpecTh 2.x is recognized
- `ignitionType` is only required for ignition delay files
- `composition_schema.yaml` now references the shared `uncertainty-metadata` definition instead of a hand-copied duplicate that had drifted to `type: float`, so a species amount accepts the same uncertainty forms as every other quantity. The definition is hoisted to its own top-level anchor in `value_unit_schema.yaml`
- Composition units accept concentrations (`mol/cm3`, `mol/m3`, `mol/dm3`, `mol/L`), the misspelling `mole faction` found in part of the ReSpecTh corpus, and a mixture of mole percent and mole fraction, which is reconciled onto mole fraction

## [0.5.0] - 2026-07-02
### Added
- Add codemeta file
- GitHub Actions CI workflow testing on Python 3.10, 3.11, 3.12, 3.13, and 3.14 on Linux, and Python 3.14 on macOS and Windows
- GitHub Actions workflow for deploying documentation to GitHub Pages, and separate workflow for publishing to PyPI on version tags using Trusted Publishers
- Updates dependency groups: `pytest-cov` in `test`,  `ruff` in `lint`
- Adds ruff, mypy, and pre-commit-hooks to `.pre-commit-config.yaml`
- `httpx2` as a direct dependency for HTTP calls in `orcid.py`
- pytest `testpaths`, `filterwarnings`, and coverage configuration in `pyproject.toml`
- `live_api` pytest marker and `tests/test_live_api.py` with contract tests that verify mock data still matches real Crossref and ORCID API responses
- GitHub Actions workflow (`.github/workflows/live-api.yml`) running live API contract tests on a weekly schedule and on manual dispatch
- `tests/_mock_data.py` centralising shared Crossref and ORCID mock data for use by both `conftest.py` and `test_live_api.py`
- `mock_orcid_api` and `mock_all_apis` fixtures in `tests/conftest.py`
- Development and testing documentation in `docs/development.rst` and `CONTRIBUTING.md`

### Changed
- replaces `os.path` with `pathlib.Path` operations
- replaces `codemeta.json` file with `CITATION.cff`
- All tests that previously called external APIs directly now use mock fixtures; `addopts = "-m 'not live_api'"` in `pyproject.toml` excludes live API tests from the default run
- switched to Coveralls for code coverage
- Directly use the Markdown formatting of the README on pypi, rather than converting to reST
- Composition type is included in the pandas data-frame resulting from `to_dataframe()`
- Migrated from `setup.py`/`setup.cfg` to `pyproject.toml` with hatchling build backend
- `pandas` moved from optional `dataframes` extra into main dependencies
- Moved source to `src/pyked/` layout; tests moved to top-level `tests/` directory
- `orcid.py` now uses `httpx2` instead of `requests` for HTTP calls, and updated to use ORCID public API v3.0
- Updated conda recipe to use `load_file_regex` for version, updated all dependency pins, require Python >= 3.10
- Updated README badges; added GitHub Actions CI badge; updated Codecov to `main` branch
- Updated `docs/conf.py`: replaced deprecated `pkg_resources` with `importlib.metadata`; replaced deprecated `autodoc_default_flags` with `autodoc_default_options`; updated intersphinx mappings; fixed `language = None` deprecation; removed legacy Travis CI environment check
- Updated paths and URLs in example notebooks and `ck-tutorial.rst`

### Fixed
- `filter` in `chemked.py` incompatible with Python 3.14; replaced with list comprehension
- ORCID URL stripping in `converters.py` used `lstrip()` (strips characters, not a prefix) causing malformed ORCIDs when Crossref returns `https://` URLs; replaced with `rfind('/')` approach consistent with `validation.py`
- Test assertions for Crossref author names updated to match current API response format
- Test path assertions for ReSpecTh conversion detail string corrected after test directory migration
- `pandas.util.testing` (removed in pandas 1.0) replaced with `pandas.testing` in test fixtures
- Removed `no_internet()` helper and `internet_missing` skip marker from `test_validation.py`; tests now mock APIs instead of skipping when offline
- Duplicate `compression_time` entry in `DataPoint` docstring causing Sphinx build failure

### Removed
- `appveyor.yml` replaced by GitHub Actions
- `requirements.txt` replaced by `pyproject.toml` dependencies
- `MANIFEST.in` not needed with hatchling build backend

## [0.4.1] - 2018-03-09
### Added
- Documentation for old versions is available on the Releases page of the docs

### Changed

### Fixed
- Doctr deploys on tags now
- Syntax changes for example files in the documentation

## [0.4.0] - 2018-03-07
### Added
- New method to instantiate a `ChemKED` class directly from a ReSpecTh XML file
- The `__version__` attribute can be imported from the top-level module
- New `time-histories` field to replace the `volume-history`. This field allows specification of several other relevant parameters besides volume.
- Added `rcm-data` field and moved `compressed-temperature`, `compressed-pressure`, and `compression-time` to this field
- Added `stroke`, `clearance`, and `compression-ratio` to the `rcm-data` field
- Added conda-forge instructions to the installation documentation
- Allow alpha versions to be specified during testing

### Changed
- Crossref lookups via Habanero now comply with the "be-nice" policy
- Removed `UnboundLocalError` from error processing for reference validation
- Switch to flake8 for style checking in CI services
- `file-author` field is now a list called `file-authors`
- ReSpecTh->ChemKED converter function now returns a dictionary, while the command-line entry points write out files
- Require Habanero>=0.6.0 to support the `mailto` argument
- Require pytest>=3.2.0 to support the `pytest.mark.filterwarnings` decorator
- Deprecate the `volume-history` field in the ChemKED YAML file and replace with `time-histories`
- ORCID lookups are now done by a function in the local `orcid.py` module, removing an external dependency
- Composition in a `DataPoint` is now stored in a dictionary of `namedtuple`s (called `Composition`) rather than a list of dictionaries

### Fixed
- Crossref lookups in the converters use the common API instance from validation
- `d/dt max extrapolated` ignition type can be converted to/from ReSpecTh
- Tests now check for appropriate warnings and ignore unrelated warnings

## [0.3.0] - 2017-10-09
### Added
- New extrapolated ignition type, where the maximum slope is extrapolated to the baseline
- Tests that the composition type is stored properly in the `DataPoint`
- `species_conversion` dictionary can be passed to the `get_cantera_mole_fraction` and `get_cantera_mass_fraction` functions to change the name of a species in the output string
- Jupyter Notebook examples of usage

### Removed
- Removes `elemental-composition` as a synonym for `atomic-composition`

### Fixed
- Fixes `test_incorrect_doi_period_at_end` docstring

### Changed
- Conda builds are now noarch - one package for all Pythons!
- pip installs now require Python compatible with 3.5
- Appveyor runs a single job and no longer builds conda packages
- Remove journal from required fields in the reference

## [0.2.1] - 2017-08-31
### Fixed
- Fixes Cantera convenience output functions

## [0.2.0] - 2017-08-10
### Added
- Adds ChemKED method to write new file, with tests
- Adds converters to and from ReSpecTh files, with tests
- Adds command-line entry points for converter scripts
- Add docs for converters

### Fixed
- `ignition_type` dictionary in `DataPoint` is now `deepcopy`d

## [0.1.6] - 2017-07-17
### Added
- Added logo files to repo
- Added `first_stage_ignition_delay`, `compressed_pressure`, and `compressed_temperature` as properties

### Changed
- Added Zenodo collection DOI to CITATION.md

## [0.1.5] - 2017-05-22
### Added
- Schema can now be split into multiple files via `!include` directive

### Fixed
- Remove Python 2.7 classifier from `setup.py`
- DataFrame output for datapoints lists with multiple compositions (i.e., a species not in all compositions)

### Changed
- Improved tests with no internet
- Improved tests with no warning

## [0.1.4] - 2017-04-21
### Added
- Add `skip_validation` keyword argument to the `ChemKED` initializer

### Removed
- Python 2.7 support is removed again

## [0.1.3] - 2017-04-13
### Added
- Add back Python 2.7 support
- Add Appveyor builds for Windows conda packages

## [0.1.2] - 2017-04-13
### Added
- Tests of the composition uncertainty in the DataPoint
- Tests of the values in the references
- Packaging for conda and PyPI
- Add Anaconda-Server badge to README

### Changed
- All fixed DOIs in CITATION.md are now specified with placeholders

## [0.1.1] - 2017-04-02
### Added
- Added Zenodo DOI badge to README
- Added CITATION file, and mention of license to README

### Fixed
- Fixed chemked-version bug in schema introduced in 0.1.0

## [0.1.0] - 2017-04-02
### Added
- First minor release of PyKED, supporting autoignition experiments.
- Basic API documentation is available via https://pr-omethe-us.github.io/PyKED/

[Unreleased]: https://github.com/pr-omethe-us/PyKED/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/pr-omethe-us/PyKED/compare/v0.4.1...v0.5.0
[0.4.1]: https://github.com/pr-omethe-us/PyKED/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/pr-omethe-us/PyKED/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/pr-omethe-us/PyKED/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/pr-omethe-us/PyKED/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/pr-omethe-us/PyKED/compare/v0.1.6...v0.2.0
[0.1.6]: https://github.com/pr-omethe-us/PyKED/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/pr-omethe-us/PyKED/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/pr-omethe-us/PyKED/compare/v0.1.3...v0.1.4
[0.1.3]: https://github.com/pr-omethe-us/PyKED/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/pr-omethe-us/PyKED/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/pr-omethe-us/PyKED/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/pr-omethe-us/PyKED/compare/75ecf67766a0be2a80e2377391fd9eca420f152c...v0.1.0
