# Change Log
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased]
### Added
- New method to instantiate a `ChemKED` class directly from a ReSpecTh XML file
- The `__version__` attribute can be imported from the top-level module

### Changed
- Crossref lookups via Habanero now comply with the "be-nice" policy
- Removed `UnboundLocalError` from error processing for reference validation
- Switch to flake8 for style checking in CI services
- `file-author` field is now a list called `file-authors`
- ReSpecTh->ChemKED converter function now returns a dictionary, while the command-line entry points write out files
- Require Habanero>=0.6.0 to support the `mailto` argument

### Fixed
- Crossref lookups in the converters use the common API instance from validation
- `d/dt max extrapolated` ignition type can be converted to/from ReSpecTh

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

[Unreleased]: https://github.com/pr-omethe-us/PyKED/compare/v0.3.0...HEAD
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
