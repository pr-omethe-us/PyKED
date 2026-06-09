"""
Test for _version.py
"""

# Standard Libraries
from importlib.metadata import version

# Local imports


def test_semantic_version():
    version("pyked")
