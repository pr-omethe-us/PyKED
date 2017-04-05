"""
Tests for the utils
"""

# Standard libraries
import os
import pkg_resources
from requests.exceptions import ConnectionError

import pytest
import yaml

from ..validation import schema, OurValidator, compare_name, property_units

v = OurValidator(schema)


class TestCompareName(object):
    """
    """
    @pytest.mark.parametrize('given, family, question_name', [
        ('Kyle', 'Niemeyer', 'Kyle Niemeyer'),
        ('Kyle', 'Niemeyer', 'K Niemeyer'),
        ('K', 'Niemeyer', 'Kyle Niemeyer'),
        ('Kyle', 'Niemeyer', 'Kyle E. Niemeyer'),
        ('K', 'Niemeyer', 'Kyle E. Niemeyer'),
        ('Kyle', 'Niemeyer', 'K. E. Niemeyer'),
        ('K', 'Niemeyer', 'K. E. Niemeyer'),
        ('Kyle', 'Niemeyer', 'K E Niemeyer'),
        ('K', 'Niemeyer', 'K E Niemeyer'),
        ('Kyle', 'Niemeyer', 'KE Niemeyer'),
        ('K', 'Niemeyer', 'KE Niemeyer'),
        ('Chih-Jen', 'Sung', 'Chih-Jen Sung'),
        ('Chih-Jen', 'Sung', 'C Sung'),
        ('C', 'Sung', 'Chih-Jen Sung'),
        ('Chih-Jen', 'Sung', 'C.-J. Sung'),
        ('Chih-Jen', 'Sung', 'C J Sung'),
        ('Chih-Jen', 'Sung', 'C-J Sung'),
        ('C J', 'Sung', 'Chih-Jen Sung'),
        ('C-J', 'Sung', 'Chih-Jen Sung'),
        ('Chih-Jen', 'Sung', 'CJ Sung'),
        ('CJ', 'Sung', 'Chih-Jen Sung'),
        ('Kyle', 'Niemeyer', 'Niemeyer, Kyle E'),
        ('Kyle', 'Niemeyer', 'Niemeyer, Kyle E.'),
        ('Chih-Jen', 'Sung', 'Sung, Chih-Jen'),
        ('Chih-Jen', 'Sung', 'Sung, C-J'),
        ('Chih-Jen', 'Sung', 'Sung, C.-J.'),
        ('Chih-Jen', 'Sung', 'Sung, C J'),
        ('Chih-Jen', 'Sung', 'Sung, C. J.'),
        ('Chih-Jen', 'Sung', 'Sung, CJ'),
        ('F. M. S.', 'Last', 'F. M. S. Last'),
        ('F. M. S.', 'Last', 'First Middle Second Last'),
        ('First Middle Second', 'Last', 'F. M. S. Last'),
        ('F. M. S.', 'Lastone Lasttwo', 'F. M. S. Lastone Lasttwo'),
        ('First Middle Second', 'Lastone Lasttwo', 'First Middle Second Lastone Lasttwo'),
        ('F. M. S.', 'Lastone-Lasttwo', 'F. M. S. Lastone-Lasttwo'),
    ])
    def test_matching_names(self, given, family, question_name):
        """ Ensure that all tested names compare correctly.
        """
        assert compare_name(given, family, question_name)


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
        assert 'Species A mass fraction must be less than 1.0' in errors
        assert 'Species B mass fraction must be greater than 0.0' in errors
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
        species = [dict(amount=[1.0, {'uncertainty-type': 'relative', 'uncertainty': 0.1}])]
        dp = dict(datapoints=[dict(composition=dict(kind='mole fraction', species=species))])
        result = v.validate(dp, update=True)
        assert result

    def test_composition_absolute_uncertainty_validation(self):
        """Ensure that quantites with absolute uncertainty are validated properly.
        """
        species = [dict(amount=[1.0, {'uncertainty-type': 'absolute', 'uncertainty': 0.1}])]
        dp = dict(datapoints=[dict(composition=dict(kind='mole fraction', species=species))])
        result = v.validate(dp, update=True)
        assert result

    def test_composition_absolute_asym_uncertainty_validation(self):
        """Ensure composition values with absolute asymmetric uncertainty are validated properly.
        """
        species = [dict(amount=[1.0, {'uncertainty-type': 'relative',
                                      'upper-uncertainty': 0.1, 'lower-uncertainty': 0.1}])]
        dp = dict(datapoints=[dict(composition=dict(kind='mole fraction', species=species))])
        result = v.validate(dp, update=True)
        assert result

    def test_composition_missing_lower_upper_uncertainty(self):
        """Test that having a single asymmetric uncertainty fails validation.

        When https://github.com/nicolaiarocci/cerberus/issues/278 is resolved,
        the errors that result from this validation should be checked to make
        sure that the missing values are caught. For now, we just check that
        the document doesn't validate.
        """
        species = [dict(amount=[1.0, {'uncertainty-type': 'relative',
                                      'upper-uncertainty': 0.1}])]
        dp = dict(datapoints=[dict(composition=dict(kind='mole fraction', species=species))])
        result = v.validate(dp, update=True)
        assert not result

        species = [dict(amount=[1.0, {'uncertainty-type': 'relative',
                                      'lower-uncertainty': 0.1}])]
        dp = dict(datapoints=[dict(composition=dict(kind='mole fraction', species=species))])
        result = v.validate(dp, update=True)
        assert not result
