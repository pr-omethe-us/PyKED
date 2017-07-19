""""
Tests for the converters
"""

# Standard libraries
import os
import pkg_resources
from requests.exceptions import ConnectionError
import socket

import pytest
import yaml

from ..converters import (get_file_metadata, get_reference, get_experiment_kind, get_common_properties,
                          get_ignition_type, get_datapoints, read_experiment, convert_ReSpecTh_to_ChemKED
                          )

class TestFileMetadata(object):
    """
    """
    
