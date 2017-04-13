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

    # remove periods
    question_name = question_name.replace('.', '')
    given_name = given_name.replace('.', '')
    family_name = family_name.replace('.', '')

    # split names by , <space> - .
    given_name = list(filter(None, re.split(r"[, \-.]+", given_name)))
    num_family_names = len(list(filter(None, re.split("[, .]+", family_name))))

    # split name in question by , <space> - .
    name_split = list(filter(None, re.split(r"[, \-.]+", question_name)))
    first_name = [name_split[0]]
    if len(name_split) > 2:
        first_name += [n for n in name_split[1:-num_family_names]]

    if len(first_name) > 1 and len(given_name) == len(first_name):
        # both have same number of first and middle names/initials
        for i in range(1, len(first_name)):
            first_name[i] = first_name[i][0]
            given_name[i] = given_name[i][0]
    elif len(given_name) != len(first_name):
        min_names = min(len(given_name), len(first_name))
        first_name = first_name[:min_names]
        given_name = given_name[:min_names]

    # first initial
    if len(first_name[0]) == 1 or len(given_name[0]) == 1:
        given_name[0] = given_name[0][0]
        first_name[0] = first_name[0][0]

    # first and middle initials combined
    if len(first_name[0]) > 1 or len(given_name[0]) > 1:
        given_name[0] = given_name[0][0]
        first_name[0] = name_split[0][0]

    # Hyphenated last name may need to be reconnected
    if num_family_names == 1 and '-' in family_name:
        num_hyphen = family_name.count('-')
        family_name_compare = '-'.join(name_split[-(num_hyphen + 1):])
    else:
        family_name_compare = ' '.join(name_split[-num_family_names:])

    return given_name == first_name and family_name == family_name_compare


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
        if 'doi' in value:
            try:
                ref = habanero.Crossref().works(ids=value['doi'])['message']
            except (HTTPError, habanero.RequestError):
                self._error(field, 'DOI not found')
                return
            # TODO: remove UnboundLocalError after habanero fixed
            except (ConnectionError, UnboundLocalError):
                warn('network not available, DOI not validated.')
                return

            # Assume that the reference returned by the DOI lookup always has a container-title
            ref_container = ref.get('container-title')[0]
            # TODO: Add other container types: value.get('journal') or value.get('report') or ...
            # note that there's a type field in the ref that is journal-article, proceedings-article
            container = value.get('journal')
            if container is None or container != ref_container:
                self._error(field, 'journal should be {}'.format(ref_container))

            # Assume that the reference returned by DOI lookup always has a year
            ref_year = ref.get('published-print') or ref.get('published-online')
            ref_year = ref_year['date-parts'][0][0]
            year = value.get('year')
            if year is None or year != ref_year:
                self._error(field, 'year should be {}'.format(ref_year))

            # Volume number might not be in the reference
            ref_volume = ref.get('volume')
            volume = value.get('volume')
            if ref_volume is None:
                if volume is not None:
                    self._error(field, 'Volume was specified in the YAML but is not present in the '
                                'DOI reference.')
            else:
                if volume is None or int(volume) != int(ref_volume):
                    self._error(field, 'volume should be {}'.format(ref_volume))

            # Pages might not be in the reference
            ref_pages = ref.get('page')
            pages = value.get('pages')
            if ref_pages is None:
                if pages is not None:
                    self._error(field, 'Pages were specified in the YAML but are not present in '
                                'the DOI reference.')
            else:
                if pages is None or pages != ref_pages:
                    self._error(field, 'pages should be {}'.format(ref_pages))

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
        else:
            self._error(field, 'composition kind must be "mole percent", "mass fraction", or '
                        '"mole fraction"')
            return False

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
