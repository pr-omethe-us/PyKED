#!/usr/bin/env python3
#
# PyKED documentation build configuration file, created by
# sphinx-quickstart on Fri Mar 31 13:06:52 2017.

import datetime
import os
import sys
from importlib.metadata import version as get_version

sys.path.insert(0, os.path.abspath(".."))

# -- General configuration ------------------------------------------------

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx.ext.todo",
    "sphinx.ext.coverage",
    "sphinx.ext.mathjax",
    "sphinx.ext.viewcode",
    "nbsphinx",
    # Workaround for https://github.com/spatialaudio/nbsphinx/issues/24
    "IPython.sphinxext.ipython_console_highlighting",
]

autodoc_default_options = {"members": True}
autoclass_content = "class"
napoleon_numpy_docstring = False
napoleon_google_docstring = True
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pandas": ("https://pandas.pydata.org/pandas-docs/stable/", None),
    "numpy": ("https://numpy.org/doc/stable/", None),
}

modindex_common_prefix = ["pyked."]

suppress_warnings = ["ref.citation"]

templates_path = ["_templates"]

source_suffix = ".rst"

master_doc = "index"

project = "PyKED"
author = "Kyle E. Niemeyer and Bryan W. Weber"
this_year = datetime.date.today().year
copyright = f"{this_year}, {author}"

try:
    release = get_version("pyked")
except Exception:
    release = "unknown"
version = ".".join(release.split(".")[:1])

language = "en"

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", ".ipynb_checkpoints"]

pygments_style = "sphinx"

todo_include_todos = True

default_role = "py:obj"

# -- Options for HTML output ----------------------------------------------

html_theme = "alabaster"

html_theme_options = {
    "github_user": "pr-omethe-us",
    "github_repo": "PyKED",
    "github_banner": True,
    "github_button": True,
    "show_powered_by": True,
}

html_static_path = ["_static"]


# -- Options for HTMLHelp output ------------------------------------------

htmlhelp_basename = "PyKEDdoc"


# -- Options for LaTeX output ---------------------------------------------

latex_elements = {}

latex_documents = [
    (
        master_doc,
        "PyKED.tex",
        "PyKED Documentation",
        "Kyle E. Niemeyer and Bryan W. Weber",
        "manual",
    ),
]


# -- Options for manual page output ---------------------------------------

man_pages = [(master_doc, "pyked", "PyKED Documentation", [author], 1)]


# -- Options for Texinfo output -------------------------------------------

texinfo_documents = [
    (
        master_doc,
        "PyKED",
        "PyKED Documentation",
        author,
        "PyKED",
        "One line description of project.",
        "Miscellaneous",
    ),
]
