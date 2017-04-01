"""
Tests for the utils
"""

# Standard libraries
import os
import pkg_resources
from requests.exceptions import ConnectionError

import pytest
import ruamel.yaml as yaml

from ..validation import schema, OurValidator, compare_name, property_units
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
        assert v.errors['reference'][0] == 'DOI not found'

    def test_invalid_ORCID(self):
        """Test for proper response to incorrect/invalid ORCID.
        """
        v.validate({'file-author': {'ORCID': '0000-0000-0000-0000', 'name': 'Kyle Niemeyer'}},
                   update=True
                   )
        assert v.errors['file-author'][0] == 'ORCID incorrect or invalid for Kyle Niemeyer'

    def test_invalid_ORCID_name(self):
        """Test for proper response to incorrect name with ORCID.
        """
        v.validate({'file-author': {'ORCID': '0000-0003-4425-7097', 'name': 'Bryan Weber'}},
                   update=True
                   )
        assert v.errors['file-author'][0] == ('Name and ORCID do not match. Name supplied: ' +
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

    def test_missing_author(self):
        """Test for proper error for missing author.
        """
        authors = [{'name': 'Kyle E Niemeyer'}, {'name': 'Kyle Brady'},
                   {'name': 'Chih-Jen Sung'}
                   ]
        v.validate(
            {'reference': {'authors': authors, 'doi': '10.1016/j.combustflame.2015.06.017'}},
            update=True,
        )
        assert ('Missing author: Xin Hui') in v.errors['reference']

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

    def test_extra_authors(self):
        """Ensure appropriate error for extra authors given.
        """
        # update=True means to ignore required keys that are left out for testing
        authors = [{'name': 'Kyle E Niemeyer'}, {'name': 'Kyle Brady'},
                   {'name': 'Chih-Jen Sung'}, {'name': 'Xin Hui'},
                   {'name': 'Bryan W Weber'}
                   ]
        v.validate(
            {'reference': {'authors': authors, 'doi': '10.1016/j.combustflame.2015.06.017'}},
            update=True,
        )
        assert ('Extra author(s) given: Bryan W Weber') in v.errors['reference']

    def test_two_authors_same_surname(self):
        """Ensure author validation can distinguish authors with same surname.
        """
        # missing Liuyan Lu from author list
        authors = [{'name': 'Zhuyin Ren'}, {'name': 'Yufeng Liu'},
                   {'name': 'Tianfeng Lu'}, {'name': 'Oluwayemisi O Oluwole'},
                   {'name': 'Graham M Goldin'}
                   ]
        v.validate(
            {'reference': {'authors': authors, 'doi': '10.1016/j.combustflame.2013.08.018'}},
            update=True,
        )
        assert ('Missing author: Liuyan Lu') in v.errors['reference']

        # now missing Tianfeng Lu from author list
        authors = [{'name': 'Zhuyin Ren'}, {'name': 'Yufeng Liu'},
                   {'name': 'Liuyan Lu'}, {'name': 'Oluwayemisi O Oluwole'},
                   {'name': 'Graham M Goldin'}
                   ]
        v.validate(
            {'reference': {'authors': authors, 'doi': '10.1016/j.combustflame.2013.08.018'}},
            update=True,
        )
        assert ('Missing author: Tianfeng Lu') in v.errors['reference']

    @pytest.fixture(scope='function')
    def properties(self, request):
        file_path = os.path.join(request.param)
        filename = pkg_resources.resource_filename(__name__, file_path)

        with open(filename, 'r') as f:
            return yaml.load(f)

    @pytest.mark.parametrize("properties", [
        'testfile_st.yaml', 'testfile_st2.yaml', 'testfile_rcm.yaml', 'testfile_required.yaml',
        'testfile_uncertainty.yaml'
    ], indirect=['properties'])
    def test_valid_yaml(self, properties):
        """Ensure ChemKED YAML is validated
        """
        assert v.validate(properties)

    @pytest.mark.parametrize("field", [
        'file-author', 'chemked-version', 'file-version', 'reference', 'experiment-type',
        'apparatus', 'datapoints',
    ])
    @pytest.mark.parametrize("properties", ['testfile_required.yaml'], indirect=["properties"])
    def test_missing_required_field(self, field, properties):
        """Ensure missing required fields causes an errors
        """
        properties.pop(field)
        v.validate(properties)
        assert v.errors[field][0] == 'required field'

    @pytest.mark.parametrize("field, sub", [
        ('reference', 'authors'), ('reference', 'journal'), ('reference', 'year'),
        ('apparatus', 'kind'), ('file-author', 'name'),
    ])
    @pytest.mark.parametrize("properties", ['testfile_required.yaml'], indirect=["properties"])
    def test_missing_required_subfield(self, field, sub, properties):
        """Ensure missing subfields causes an errors
        """
        properties[field].pop(sub)
        v.validate(properties)
        assert v.errors[field][0][sub][0] == 'required field'

    @pytest.mark.parametrize("properties", ['testfile_required.yaml'], indirect=["properties"])
    def test_missing_authors(self, properties):
        """Ensure the authors list contains data
        """
        properties['reference']['authors'] = []
        v.validate(properties)
        assert v.errors['reference'][0]['authors'][0] == 'min length is 1'

    @pytest.mark.parametrize("properties", ['testfile_required.yaml'], indirect=["properties"])
    def test_missing_datapoints(self, properties):
        """Ensure the datapoints list contains data
        """
        properties['datapoints'] = []
        v.validate(properties)
        assert v.errors['datapoints'][0] == 'min length is 1'

    def test_invalid_experiment_type(self):
        """Ensure that an invalid experiment type is an error
        """
        # update=True means to ignore required keys that are left out for testing
        v.validate({'experiment-type': 'invalid experiment'}, update=True)
        assert v.errors['experiment-type'][0] == 'unallowed value invalid experiment'

    @pytest.mark.parametrize("valid_type", [
        'ignition delay',
    ])
    def test_valid_experiment_types(self, valid_type):
        """Ensure that all the valid experiment types are validated
        """
        # update=True means to ignore required keys that are left out for testing
        assert v.validate({'experiment-type': valid_type}, update=True)

    @pytest.mark.parametrize("quantity, unit", property_units.items())
    def test_incompatible_quantity(self, quantity, unit):
        """Ensure that incompatible quantities are validation errors
        """
        quant_schema = {quantity: {'type': 'list', 'isvalid_quantity': True}}
        v = OurValidator(quant_schema)
        v.validate({quantity: ['-999 {}'.format(unit)]})
        assert v.errors[quantity][0] == 'value must be greater than 0.0 {}'.format(unit)

    @pytest.mark.parametrize("quantity, unit", property_units.items())
    def test_dimensionality_error_quantity(self, quantity, unit):
        """Ensure that dimensionality errors are validation errors
        """
        quant_schema = {quantity: {'type': 'list', 'isvalid_quantity': True}}
        v = OurValidator(quant_schema)
        v.validate({quantity: ['1.0 {}'.format('candela*ampere')]})
        assert v.errors[quantity][0] == 'incompatible units; should be consistent with {}'.format(unit)

    @pytest.mark.parametrize("quantity, unit", [('volume', 'meter**3'), ('time', 'second')])
    def test_dimensionality_error_unit(self, quantity, unit):
        """Ensure that dimensionality errors in units are validation errors
        """
        unit_schema = {quantity: {'type': 'dict', 'isvalid_unit': True}}
        v = OurValidator(unit_schema)
        v.validate({quantity: {'units': 'candela*ampere'}})
        assert v.errors[quantity][0] == 'incompatible units; should be consistent with {}'.format(unit)

    @pytest.mark.parametrize("properties", ['testfile_bad.yaml'], indirect=["properties"])
    def test_mole_fraction_bad_sum(self, properties):
        """Ensure mole fractions that do not sum to 1.0 raise error
        """
        v.validate(properties)
        assert ('Species mole fractions do not sum to 1.0: 0.300000' in
                v.errors['datapoints'][0][0][0]['composition']
                )

    @pytest.mark.parametrize("properties", ['testfile_bad.yaml'], indirect=["properties"])
    def test_mass_fraction_bad_sum(self, properties):
        """Ensure mass fractions that do not sum to 1.0 raise validation error
        """
        v.validate(properties)
        assert ('Species mass fractions do not sum to 1.0: 0.300000' in
                v.errors['datapoints'][0][1][0]['composition']
                )

    @pytest.mark.parametrize("properties", ['testfile_bad.yaml'], indirect=["properties"])
    def test_mole_percent_bad_sum(self, properties):
        """Ensure mole percent that do not sum to 100. raise validation error
        """
        v.validate(properties)
        assert ('Species mole percents do not sum to 100.0: 30.000000' in
                v.errors['datapoints'][0][2][0]['composition']
                )

    def test_composition_bounded(self):
        """Ensure that composition bounds errors fail validation.
        """
        v.validate({'datapoints': [{'composition':
            {'kind': 'mass fraction',
             'species': [{'species-name': 'A', 'amount': [1.2]},
                         {'species-name': 'B', 'amount': [-0.1]}]
             }}]}, update=True)
        errors = v.errors['datapoints'][0][0][0]['composition']
        assert 'Species A mass fraction is out of bounds.' in errors
        assert 'Species B mass fraction is out of bounds.' in errors
        assert 'Species mass fractions do not sum to 1.0: 1.100000' in errors

    @pytest.mark.parametrize("quantity, unit", property_units.items())
    def test_relative_uncertainty_validation(self, quantity, unit):
        """Ensure that quantites with relative uncertainty are validated properly.
        """
        uncertainty_schema = {quantity: {'type': 'list', 'isvalid_uncertainty': True}}
        v = OurValidator(uncertainty_schema)
        assert v.validate({quantity: ['1.0 {}'.format(unit),
                                      {'uncertainty-type': 'relative', 'uncertainty': 0.1}]})

    @pytest.mark.parametrize("quantity, unit", property_units.items())
    def test_absolute_uncertainty_validation(self, quantity, unit):
        """Ensure that quantites with absolute uncertainty are validated properly.
        """
        uncertainty_schema = {quantity: {'type': 'list', 'isvalid_uncertainty': True}}
        v = OurValidator(uncertainty_schema)
        assert v.validate({quantity: ['1.0 {}'.format(unit),
                                      {'uncertainty-type': 'absolute',
                                       'uncertainty': '0.1 {}'.format(unit)}]})

    @pytest.mark.parametrize("quantity, unit", property_units.items())
    def test_absolute_asym_uncertainty_validation(self, quantity, unit):
        """Ensure that quantites with absolute asymmetric uncertainty are validated properly.
        """
        uncertainty_schema = {quantity: {'type': 'list', 'isvalid_uncertainty': True}}
        v = OurValidator(uncertainty_schema)
        assert v.validate({quantity: ['1.0 {}'.format(unit),
                                      {'uncertainty-type': 'absolute',
                                       'upper-uncertainty': '0.1 {}'.format(unit),
                                       'lower-uncertainty': '0.1 {}'.format(unit)}]})

    def test_missing_lower_upper_uncertainty(self):
        """Test that having a single asymmetric uncertainty fails validation.

        When https://github.com/nicolaiarocci/cerberus/issues/278 is resolved,
        the errors that result from this validation should be checked to make
        sure that the missing values are caught. For now, we just check that
        the document doesn't validate.
        """
        result = v.validate({'datapoints': [{'temperature': ['1000 kelvin',
                                                             {'uncertainty-type': 'relative',
                                                              'upper-uncertainty': 0.1}]}]},
                            update=True)
        assert not result

        result = v.validate({'datapoints': [{'temperature': ['1000 kelvin',
                                                             {'uncertainty-type': 'relative',
                                                              'lower-uncertainty': 0.1}]}]},
                            update=True)
        assert not result

    @pytest.mark.parametrize("quantity, unit", property_units.items())
    def test_incompatible_sym_uncertainty(self, quantity, unit):
        """Ensure that incompatible quantities are validation errors for symmetric uncertainties
        """
        quant_schema = {quantity: {'type': 'list', 'isvalid_uncertainty': True}}
        v = OurValidator(quant_schema)
        v.validate({quantity: ['999 {}'.format(unit),
                               {'uncertainty-type': 'absolute',
                                'uncertainty': '-999 {}'.format(unit)}
                               ]
                    })
        assert v.errors[quantity][0] == 'value must be greater than 0.0 {}'.format(unit)

    @pytest.mark.parametrize("quantity, unit", property_units.items())
    def test_dimensionality_error_sym_uncertainty(self, quantity, unit):
        """Ensure that dimensionality errors are validation errors for symmetric uncertainties
        """
        quant_schema = {quantity: {'type': 'list', 'isvalid_uncertainty': True}}
        v = OurValidator(quant_schema)
        v.validate({quantity: ['999 {}'.format(unit),
                               {'uncertainty-type': 'absolute',
                                'uncertainty': '1 {}'.format('candela*ampere')}]})
        assert v.errors[quantity][0] == 'incompatible units; should be consistent with {}'.format(unit)

    @pytest.mark.parametrize("quantity, unit", property_units.items())
    def test_incompatible_asym_uncertainty(self, quantity, unit):
        """Ensure that incompatible quantities are validation errors for asymmetric uncertainties
        """
        quant_schema = {quantity: {'type': 'list', 'isvalid_uncertainty': True}}
        v = OurValidator(quant_schema)
        v.validate({quantity: ['999 {}'.format(unit),
                               {'uncertainty-type': 'absolute',
                                'upper-uncertainty': '-999 {}'.format(unit),
                                'lower-uncertainty': '-999 {}'.format(unit)}
                               ]
                    })
        assert v.errors[quantity][0] == 'value must be greater than 0.0 {}'.format(unit)

    @pytest.mark.parametrize("quantity, unit", property_units.items())
    def test_dimensionality_error_asym_uncertainty(self, quantity, unit):
        """Ensure that dimensionality errors are validation errors for asymmetric uncertainties
        """
        quant_schema = {quantity: {'type': 'list', 'isvalid_uncertainty': True}}
        v = OurValidator(quant_schema)
        v.validate({quantity: ['999 {}'.format(unit),
                               {'uncertainty-type': 'absolute',
                                'upper-uncertainty': '1 {}'.format('candela*ampere'),
                                'lower-uncertainty': '1 {}'.format('candela*ampere')}
                               ]
                    })
        assert v.errors[quantity][0] == 'incompatible units; should be consistent with {}'.format(unit)

    def test_composition_relative_uncertainty_validation(self):
        """Ensure composition with relative uncertainty are validated properly.
        """
        result = v.validate({'datapoints': [{'composition': {'kind': 'mole fraction',
                                                             'species': [{'amount': [1.0,
                                                             {'uncertainty-type': 'relative',
                                                              'uncertainty': 0.1}]}]
                                                             }}]
                             }, update=True)
        assert result

    def test_composition_absolute_uncertainty_validation(self):
        """Ensure that quantites with absolute uncertainty are validated properly.
        """
        result = v.validate({'datapoints': [{'composition': {'kind': 'mole fraction',
                                                             'species': [{'amount': [1.0,
                                                             {'uncertainty-type': 'absolute',
                                                              'uncertainty': 0.1}]}]
                                                             }}]
                             }, update=True)
        assert result

    def test_composition_absolute_asym_uncertainty_validation(self):
        """Ensure composition values with absolute asymmetric uncertainty are validated properly.
        """
        result = v.validate({'datapoints': [{'composition': {'kind': 'mole fraction',
                                                             'species': [{'amount': [1.0,
                                                             {'uncertainty-type': 'relative',
                                                              'upper-uncertainty': 0.1,
                                                              'lower-uncertainty': 0.1}]}]
                                                             }}]
                             }, update=True)
        assert result

    def test_composition_missing_lower_upper_uncertainty(self):
        """Test that having a single asymmetric uncertainty fails validation.

        When https://github.com/nicolaiarocci/cerberus/issues/278 is resolved,
        the errors that result from this validation should be checked to make
        sure that the missing values are caught. For now, we just check that
        the document doesn't validate.
        """
        result = v.validate({'datapoints': [{'composition': {'kind': 'mole fraction',
                                                             'species': [{'amount': [1.0,
                                                             {'uncertainty-type': 'relative',
                                                              'upper-uncertainty': 0.01}]}]
                                                             }}]
                             }, update=True)
        assert not result

        result = v.validate({'datapoints': [{'composition': {'kind': 'mole fraction',
                                                             'species': [{'amount': [1.0,
                                                             {'uncertainty-type': 'relative',
                                                              'lower-uncertainty': 0.01}]}]
                                                             }}]
                             }, update=True)
        assert not result
