"""Validation class for ChemKED schema.
"""

from functools import reduce
from warnings import warn
import re

import pkg_resources
import yaml

import numpy as np
import pint
from requests.exceptions import HTTPError, ConnectionError
from cerberus import Validator
import habanero
from orcid import SearchAPI

# Local imports
from .utils import units, Q_

orcid_api = SearchAPI(sandbox=False)

# Load the ChemKED schema definition file
schema_file = pkg_resources.resource_filename(__name__, 'chemked_schema.yaml')
with open(schema_file, 'r') as f:
    schema = yaml.safe_load(f)

# These top-level keys in the schema serve as references for lower-level keys.
# They are removed to prevent conflicts due to required variables, etc.
for key in ['author', 'value-unit-required', 'value-unit-optional',
            'composition', 'ignition-type', 'value-with-uncertainty',
            'value-without-uncertainty',
            ]:
    del schema[key]

# SI units for available value-type properties
property_units = {'temperature': 'kelvin',
                  'pressure': 'pascal',
                  'ignition-delay': 'second',
                  'pressure-rise': '1.0 / second',
                  'compression-time': 'second',
                  'volume': 'meter**3',
                  'time': 'second',
                  }


def compare_name(given_name, family_name, question_name):
    """Compares a name in question to a specified name separated into given and family.

    The name in question ``question_name`` can be of varying format, including
    "Kyle E. Niemeyer", "Kyle Niemeyer", "K. E. Niemeyer", "KE Niemeyer", and
    "K Niemeyer". Other possibilities include names with hyphens such as
    "Chih-Jen Sung", "C. J. Sung", "C-J Sung".

    Examples:
        >>> compare_name('Kyle', 'Niemeyer', 'Kyle E Niemeyer')
        True
        >>> compare_name('Chih-Jen', 'Sung', 'C-J Sung')
        True

    Args:
        given_name (`str`): Given (or first) name to be checked against.
        family_name (`str`): Family (or last) name to be checked against.
        question_name (`str`): The whole name in question.

    Returns:
        `bool`: The return value. True for successful comparison, False otherwise.
    """
    # lowercase everything
    given_name = given_name.lower()
    family_name = family_name.lower()
    question_name = question_name.lower()

    # rearrange names given as "last, first middle"
    if ',' in question_name:
        name_split = question_name.split(',')
        name_split.reverse()
        question_name = ' '.join(name_split).strip()

    # split name in question by , <space> - .
    name_split = list(filter(None, re.split("[, \-.]+", question_name)))
    first_name = [name_split[0]]
    if len(name_split) == 3:
        first_name += [name_split[1]]

    given_name = list(filter(None, re.split("[, \-.]+", given_name)))

    if len(first_name) == 2 and len(given_name) == 2:
        # both have first and middle name/initial
        first_name[1] = first_name[1][0]
        given_name[1] = given_name[1][0]
    elif len(given_name) == 2 and len(first_name) == 1:
        del given_name[1]
    elif len(first_name) == 2 and len(given_name) == 1:
        del first_name[1]

    # first initial
    if len(first_name[0]) == 1 or len(given_name[0]) == 1:
        given_name[0] = given_name[0][0]
        first_name[0] = first_name[0][0]

    # first and middle initials combined
    if len(first_name[0]) == 2 or len(given_name[0]) == 2:
        given_name[0] = given_name[0][0]
        first_name[0] = name_split[0][0]

    return given_name == first_name and family_name == name_split[-1]


class OurValidator(Validator):
    """Custom validator with rules for Quantities and references.
    """
    def _validate_isvalid_unit(self, isvalid_unit, field, value):
        """Checks for appropriate units using Pint unit registry.

        Args:
            isvalid_unit (`bool`): flag from schema indicating units to be checked.
            field (`str`): property associated with units in question.
            value (`dict`): dictionary of values from file associated with this property.

        The rule's arguments are validated against this schema:
            {'isvalid_unit': {'type': 'bool'}, 'field': {'type': 'str'},
             'value': {'type': 'dict'}}
        """
        quantity = 1.0 * units(value['units'])
        try:
            quantity.to(property_units[field])
        except pint.DimensionalityError:
            self._error(field, 'incompatible units; should be consistent '
                        'with ' + property_units[field]
                        )

    def _validate_isvalid_quantity(self, isvalid_quantity, field, value):
        """Checks for valid given value and appropriate units.

        Args:
            isvalid_quantity (`bool`): flag from schema indicating quantity to be checked.
            field (`str`): property associated with quantity in question.
            value (`str`): string of the value of the quantity

        The rule's arguments are validated against this schema:
            {'isvalid_quantity': {'type': 'bool'}, 'field': {'type': 'str'},
             'value': {'type': 'dict'}}
        """
        quantity = Q_(value[0])
        low_lim = 0.0 * units(property_units[field])

        try:
            if quantity <= low_lim:
                self._error(
                    field, 'value must be greater than 0.0 {}'.format(property_units[field]),
                )
        except pint.DimensionalityError:
            self._error(field, 'incompatible units; should be consistent '
                        'with ' + property_units[field]
                        )

    def _validate_isvalid_uncertainty(self, isvalid_uncertainty, field, value):
        """Checks for valid given value and appropriate units with uncertainty.

        Args:
            isvalid_uncertainty (`bool`): flag from schema indicating uncertainty to be checked
            field (`str`): property associated with the quantity in question.
            value (`list`): list with the string of the value of the quantity and a dictionary of
                the uncertainty

        The rule's arguments are validated against this schema:
            {'isvalid_uncertainty': {'type': 'bool'}, 'field': {'type': 'str'},
             'value': {'type': 'dict'}}
        """
        self._validate_isvalid_quantity(True, field, value)

        # This len check is necessary for reasons that aren't quite clear to me
        # Cerberus calls this validation method even when lists have only one element
        # and should therefore be validated only by isvalid_quantity
        if len(value) > 1 and value[1]['uncertainty-type'] != 'relative':
            if value[1].get('uncertainty') is not None:
                self._validate_isvalid_quantity(True, field, [value[1]['uncertainty']])

            if value[1].get('upper-uncertainty') is not None:
                self._validate_isvalid_quantity(True, field, [value[1]['upper-uncertainty']])

            if value[1].get('lower-uncertainty') is not None:
                self._validate_isvalid_quantity(True, field, [value[1]['lower-uncertainty']])

    def _validate_isvalid_reference(self, isvalid_reference, field, value):
        """Checks valid reference metadata using DOI (if present).

        Todo:
            * remove UnboundLocalError from exception handling

        Args:
            isvalid_reference (`bool`): flag from schema indicating reference to be checked.
            field (`str`): 'reference'
            value (`dict`): dictionary of reference metadata.

        The rule's arguments are validated against this schema:
            {'isvalid_reference': {'type': 'bool'}, 'field': {'type': 'str'},
             'value': {'type': 'dict'}}

        """
        if isvalid_reference and 'doi' in value:
            try:
                ref = habanero.Crossref().works(ids=value['doi'])['message']
            except (HTTPError, habanero.RequestError):
                self._error(field, 'DOI not found')
                return
            # TODO: remove UnboundLocalError after habanero fixed
            except (ConnectionError, UnboundLocalError):
                warn('network not available, DOI not validated.')
                return

            # check journal name
            if ('journal' in value) and (value['journal'] not in ref['container-title']):
                self._error(field, 'journal does not match: ' +
                            ', '.join(ref['container-title'])
                            )
            # check year
            pub_year = (ref.get('published-print')
                        if 'published-print' in ref
                        else ref.get('published-online')
                        )['date-parts'][0][0]

            if ('year' in value) and (value['year'] != pub_year):
                self._error(field, 'year should be ' + str(pub_year))

            # check volume number
            if (('volume' in value) and ('volume' in ref) and
                    (value['volume'] != int(ref['volume']))):
                self._error(field, 'volume number should be ' + ref['volume'])

            # check pages
            if ('pages' in value) and ('page' in ref) and value['pages'] != ref['page']:
                self._error(field, 'pages should be ' + ref['page'])

            # check that all authors present
            authors = value['authors'][:]
            author_names = [a['name'] for a in authors]
            for author in ref['author']:
                # find using family name
                author_match = next(
                    (a for a in authors if
                     compare_name(author['given'], author['family'], a['name'])
                     ),
                    None
                    )
                # error if missing author in given reference information
                if author_match is None:
                    self._error(field, 'Missing author: ' +
                                ' '.join([author['given'], author['family']])
                                )
                else:
                    author_names.remove(author_match['name'])

                    # validate ORCID if given
                    orcid = author.get('ORCID')
                    if orcid:
                        # Crossref may give ORCID as http://orcid.org/####-####-####-####
                        # so need to strip the leading URL
                        orcid = orcid[orcid.rfind('/') + 1:]

                        if 'ORCID' in author_match:
                            if author_match['ORCID'] != orcid:
                                self._error(
                                    field, author_match['name'] + ' ORCID does ' +
                                    'not match that in reference. Reference: ' +
                                    orcid + '. Given: ' + author_match['ORCID']
                                    )
                        else:
                            # ORCID not given, suggest adding it
                            warn('ORCID ' + orcid + ' missing for ' + author_match['name'])

            # check for extra names given
            if len(author_names) > 0:
                self._error(field, 'Extra author(s) given: ' +
                            ', '.join(author_names)
                            )

    def _validate_isvalid_orcid(self, isvalid_orcid, field, value):
        """Checks for valid ORCID if given.

        Args:
            isvalid_orcid (`bool`): flag from schema indicating ORCID to be checked.
            field (`str`): 'author'
            value (`dict`): dictionary of author metadata.

        The rule's arguments are validated against this schema:
            {'isvalid_orcid': {'type': 'bool'}, 'field': {'type': 'str'},
             'value': {'type': 'dict'}}

        """
        if isvalid_orcid and 'ORCID' in value:
            try:
                res = orcid_api.search_public('orcid:' + value['ORCID'])
            except ConnectionError:
                warn('network not available, ORCID not validated.')
                return

            # Return error if no results are found for the given ORCID
            if res['orcid-search-results']['num-found'] == 0:
                self._error(field, 'ORCID incorrect or invalid for ' +
                            value['name']
                            )
                return

            maplist = ['orcid-search-results', 'orcid-search-result', 0,
                       'orcid-profile', 'orcid-bio', 'personal-details',
                       'family-name', 'value'
                       ]
            family_name = reduce(lambda d, k: d[k], maplist, res)
            maplist[-2] = 'given-names'
            given_name = reduce(lambda d, k: d[k], maplist, res)

            if not compare_name(given_name, family_name, value['name']):
                self._error(field, 'Name and ORCID do not match. Name supplied: ' +
                            value['name'] + '. Name associated with ORCID: ' +
                            ' '.join([given_name, family_name])
                            )

    def _validate_isvalid_composition(self, isvalid_composition, field, value):
        """Checks for valid specification of composition.

        Args:
            isvalid_composition (bool): flag from schema indicating
                composition to be checked.
            field (str): 'composition'
            value (dict): dictionary of composition

        The rule's arguments are validated against this schema:
            {'isvalid_composition': {'type': 'bool'}, 'field': {'type': 'str'},
             'value': {'type': 'dict'}}
        """
        sum_amount = 0.0
        if value['kind'] in ['mass fraction', 'mole fraction']:
            low_lim = 0.0
            up_lim = 1.0
            total_amount = 1.0
        elif value['kind'] in ['mole percent']:
            low_lim = 0.0
            up_lim = 100.0
            total_amount = 100.0

        for sp in value['species']:
            amount = sp['amount'][0]
            sum_amount += amount

            # Check that amount within bounds, based on kind specified
            if amount < low_lim:
                self._error(field, 'Species ' + sp['species-name'] + ' ' +
                            value['kind'] + ' must be greater than {:.1f}'.format(low_lim)
                            )
            elif amount > up_lim:
                self._error(field, 'Species ' + sp['species-name'] + ' ' +
                            value['kind'] + ' must be less than {:.1f}'.format(up_lim)
                            )

        # Make sure mole/mass fraction sum to 1
        if not np.isclose(total_amount, sum_amount):
            self._error(field, 'Species ' + value['kind'] +
                        's do not sum to {:.1f}: '.format(total_amount) +
                        '{:f}'.format(sum_amount)
                        )
        # TODO: validate InChI, SMILES, or elemental-composition/atomic-composition
