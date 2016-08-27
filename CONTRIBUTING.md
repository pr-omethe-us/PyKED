# Contributing

We welcome contributions in the form of bug reports, bug fixes, improvements to the documentation, ideas for enhancements (or the enhancements themselves!).

You can find a [list of current issues](https://github.com/Niemeyer-Research-Group/ChemKED/issues) in the project's GitHub repo. Feel free to tackle any existing bugs or enhancement ideas by submitting a [pull request](https://github.com/Niemeyer-Research-Group/ChemKED/pulls).

## Bug Reports

 * Please include a short (but detailed) Python snippet or explanation for reproducing the problem. Attach or include a link to any input files that will be needed to reproduce the error.
 * Explain the behavior you expected, and how what you got differed.

## Pull Requests

 * **Make sure the test suite passes** on your computer, and that test coverage doesn't go down. To do this run `pytest -vv --cov=./` from the top-level directory.
 * *Always* add tests and docs for your code.
 * Please reference relevant GitHub issues in your commit message using `GH123` or `#123`.
 * Changes should be [PEP8](https://www.python.org/dev/peps/pep-0008/) and [PEP257](https://www.python.org/dev/peps/pep-0257/) compatible.
 * Keep style fixes to a separate commit to make your pull request more readable.
 * Docstrings are required and should follow the [Google style](http://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html).
 * When you start working on a pull request, start by creating a new branch pointing at the latest commit on [GitHub master](https://github.com/Niemeyer-Research-Group/ChemKED/tree/master).
 * The copyright policy is detailed in the [`LICENSE`](https://github.com/Niemeyer-Research-Group/ChemKED/blob/master/LICENSE).

## Meta

Thanks to the useful [contributing guide of pyrk](https://github.com/pyrk/pyrk/blob/master/CONTRIBUTING.md), which served as an inspiration and starting point for this guide.
