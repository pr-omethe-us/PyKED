"""
Tests for the utils
"""

# Standard libraries
import os
import pkg_resources
from requests.exceptions import ConnectionError

import pytest
try:
    import ruamel.yaml as yaml
except ImportError:
    import yaml

from ..validation import schema, OurValidator, compare_name
print(schema)

v = OurValidator(schema)


class TestCompareName(object):
    """
    """
    def test_matching_name(self):
        """ Kyle Niemeyer vs Kyle Niemeyer
        """
        assert compare_name('Kyle', 'Niemeyer', 'Kyle Niemeyer')

    def test_matching_first_initial(self):
        """ Kyle Niemeyer vs K Niemeyer
        """
        assert compare_name('Kyle', 'Niemeyer', 'K Niemeyer')
        assert compare_name('K', 'Niemeyer', 'Kyle Niemeyer')

    def test_matching_full_name(self):
        """ Kyle Niemeyer vs Kyle E. Niemeyer
        """
        assert compare_name('Kyle', 'Niemeyer', 'Kyle E. Niemeyer')
        assert compare_name('K', 'Niemeyer', 'Kyle E. Niemeyer')

    def test_matching_initials_periods(self):
        """ Kyle Niemeyer vs K. E. Niemeyer
        """
        assert compare_name('Kyle', 'Niemeyer', 'K. E. Niemeyer')
        assert compare_name('K', 'Niemeyer', 'K. E. Niemeyer')

    def test_matching_initials(self):
        """ Kyle Niemeyer vs K E Niemeyer
        """
        assert compare_name('Kyle', 'Niemeyer', 'K E Niemeyer')
        assert compare_name('K', 'Niemeyer', 'K E Niemeyer')

    def test_matching_initials_combined(self):
        """ Kyle Niemeyer vs KE Niemeyer
        """
        assert compare_name('Kyle', 'Niemeyer', 'KE Niemeyer')
        assert compare_name('K', 'Niemeyer', 'KE Niemeyer')

    def test_matching_name_hyphen(self):
        """ Chih-Jen Sung vs Chih-Jen Sung
        """
        assert compare_name('Chih-Jen', 'Sung', 'Chih-Jen Sung')

    def test_matching_first_initial_hyphen(self):
        """ Chih-Jen Sung vs C Sung
        """
        assert compare_name('Chih-Jen', 'Sung', 'C Sung')
        assert compare_name('C', 'Sung', 'Chih-Jen Sung')

    def test_matching_initials_periods_hyphen(self):
        """ Chih-Jen Sung vs C.-J. Sung
        """
        assert compare_name('Chih-Jen', 'Sung', 'C.-J. Sung')

    def test_matching_initials_hyphens(self):
        """ Chih-Jen Sung vs C J Sung
        """
        assert compare_name('Chih-Jen', 'Sung', 'C J Sung')
        assert compare_name('Chih-Jen', 'Sung', 'C-J Sung')
        assert compare_name('C J', 'Sung', 'Chih-Jen Sung')
        assert compare_name('C-J', 'Sung', 'Chih-Jen Sung')

    def test_matching_initials_combined_hyphen(self):
        """ Chih-Jen Sung vs CJ Sung
        """
        assert compare_name('Chih-Jen', 'Sung', 'CJ Sung')
        assert compare_name('CJ', 'Sung', 'Chih-Jen Sung')

    def test_matching_name_comma(self):
        """ Kyle Niemeyer vs Niemeyer, Kyle E
        """
        assert compare_name('Kyle', 'Niemeyer', 'Niemeyer, Kyle E')
        assert compare_name('Kyle', 'Niemeyer', 'Niemeyer, Kyle E.')

    def test_matching_name_comma_hyphen(self):
        """ Chih-Jen Sung vs Sung, Chih-Jen
        """
        assert compare_name('Chih-Jen', 'Sung', 'Sung, Chih-Jen')

    def test_matching_name_comma_hyphen_initials(self):
        """ Chih-Jen Sung vs Sung, C-J
        """
        assert compare_name('Chih-Jen', 'Sung', 'Sung, C-J')
        assert compare_name('Chih-Jen', 'Sung', 'Sung, C.-J.')
        assert compare_name('Chih-Jen', 'Sung', 'Sung, C J')
        assert compare_name('Chih-Jen', 'Sung', 'Sung, C. J.')
        assert compare_name('Chih-Jen', 'Sung', 'Sung, CJ')


class TestValidator(object):
    """
    """
    @pytest.fixture(scope='function')
    def disable_socket(self):
        """Disables socket to prevent network access.
        """
        import socket
        old_socket = socket.socket

        def guard(*args, **kwargs):
            raise ConnectionError("No internet")
        socket.socket = guard
        yield
        socket.socket = old_socket

    def test_doi_missing_internet(self, disable_socket):
        """Ensure that DOI validation fails gracefully with no Internet.
        """
        with pytest.warns(UserWarning):
            v.validate({'reference': {'doi': '10.1016/j.combustflame.2009.12.022'}}, update=True)

    def test_orcid_missing_internet(self, disable_socket):
        """Ensure that ORCID validation fails gracefully with no Internet.
        """
        with pytest.warns(UserWarning):
            v.validate({'file-author': {'ORCID': '0000-0003-4425-7097'}}, update=True)

    def test_invalid_DOI(self):
        """Test for proper response to incorrect/invalid DOI.
        """
        v.validate({'reference': {'doi': '10.1000/invalid.doi'}}, update=True)
        assert v.errors['reference'] == 'DOI not found'

    def test_invalid_ORCID(self):
        """Test for proper response to incorrect/invalid ORCID.
        """
        v.validate({'file-author': {'ORCID': '0000-0000-0000-0000', 'name': 'Kyle Niemeyer'}},
                   update=True
                   )
        assert v.errors['file-author'] == 'ORCID incorrect or invalid for Kyle Niemeyer'

    def test_invalid_ORCID_name(self):
        """Test for proper response to incorrect name with ORCID.
        """
        v.validate({'file-author': {'ORCID': '0000-0003-4425-7097', 'name': 'Bryan Weber'}},
                   update=True
                   )
        assert v.errors['file-author'] == ('Name and ORCID do not match. Name supplied: ' +
                                           'Bryan Weber. Name associated with ORCID: ' +
                                           'Kyle Niemeyer'
                                           )

    def test_suggest_ORCID(self):
        """Test for proper suggestion for missing ORCID.
        """
        authors = [{'name': 'Kyle E Niemeyer'},
                   {'name': 'Kyle Brady', 'ORCID': '0000-0002-4664-3680'},
                   {'name': 'Chih-Jen Sung'}, {'name': 'Xin Hui'}
                   ]
        with pytest.warns(UserWarning):
            v.validate(
                {'reference': {'authors': authors, 'doi': '10.1016/j.combustflame.2015.06.017'}},
                update=True,
            )

    def test_valid_reference_authors(self):
        """Ensure correct validation of reference authors
        """
        # update=True means to ignore required keys that are left out for testing
        authors = [{'name': 'Kyle E Niemeyer', 'ORCID': '0000-0003-4425-7097'},
                   {'name': 'Bryan W Weber', 'ORCID': '0000-0003-0815-9270'},
                   ]
        assert v.validate({'reference': {'authors': authors}}, update=True)

    def test_unmatching_ORCIDs(self):
        """Ensure appropriate error for author ORCID not matching that via DOI
        """
        # update=True means to ignore required keys that are left out for testing
        authors = [{'name': 'Kyle E Niemeyer', 'ORCID': '0000-0003-0815-9270'},
                   {'name': 'Kyle Brady', 'ORCID': '0000-0002-4664-3680'},
                   {'name': 'Chih-Jen Sung'}, {'name': 'Xin Hui'}
                   ]
        v.validate(
            {'reference': {'authors': authors, 'doi': '10.1016/j.combustflame.2015.06.017'}},
            update=True,
        )
        assert ('Kyle E Niemeyer ORCID does not match '
                'that in reference. Reference: 0000-0003-4425-7097. '
                'Given: ' + authors[0]['ORCID']
                ) in v.errors['reference']

    def test_valid_shock_tube(self):
        """Ensure shock tube experiment can be detected.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with open(filename, 'r') as f:
            properties = yaml.load(f)

        if not v.validate(properties):
            print(v.errors)
            assert False
        else:
            assert True

    def test_valid_shock_tube_with_pressure_rise(self):
        """Ensure shock tube experiment can be detected with pressure rise.
        """
        file_path = os.path.join('testfile_st2.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with open(filename, 'r') as f:
            properties = yaml.load(f)

        if not v.validate(properties):
            print(v.errors)
            assert False
        else:
            assert True

    def test_valid_rcm_experiment(self):
        """Ensure RCM experiment can be detected.
        """
        file_path = os.path.join('testfile_rcm.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with open(filename, 'r') as f:
            properties = yaml.load(f)

        if not v.validate(properties):
            print(v.errors)
            assert False
        else:
            assert True

    def test_invalid_experiment_type(self):
        """Ensure that an invalid experiment type raises an exception.
        """
        # update=True means to ignore required keys that are left out for testing
        v.validate({'experiment-type': 'invalid experiment'}, update=True)
        assert v.errors['experiment-type'] == 'unallowed value invalid experiment'

    def test_valid_experiment_types(self):
        """Ensure that all the valid experiment types are validated
        """
        # update=True means to ignore required keys that are left out for testing
        valid_experiment_types = ['ignition delay']
        for exp in valid_experiment_types:
            assert v.validate({'experiment-type': exp}, update=True)
