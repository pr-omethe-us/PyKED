""""
Tests for the converters
"""

# Standard libraries
import os
import pkg_resources
from requests.exceptions import ConnectionError
import socket
from tempfile import TemporaryDirectory
import xml.etree.ElementTree as etree
from shutil import copy

import pytest
import numpy.random
from numpy.testing import assert_allclose


# Local imports
from ..converters import (ParseError, KeywordError, MissingElementError,
                          MissingAttributeError
                          )
from ..converters import (get_file_metadata, get_reference, get_experiment_kind,
                          get_common_properties, get_ignition_type, get_datapoints,
                          ReSpecTh_to_ChemKED, main, respth2ck, ck2respth
                          )
from .._version import __version__
from ..chemked import ChemKED


class TestErrors(object):
    """
    """
    def test_parse_error(self):
        """(Very) basic test of ParseError.
        """
        with pytest.raises(ParseError) as excinfo:
            raise ParseError('this is an error')
        assert 'this is an error' in str(excinfo.value)

    def test_keyword_error(self):
        """Basic test of KeywordError.
        """
        with pytest.raises(KeywordError) as excinfo:
            raise KeywordError('this is a test')
        assert 'Error: this is a test.' in str(excinfo.value)

    def test_missing_element_error(self):
        """Basic test of MissingElementError.
        """
        with pytest.raises(MissingElementError) as excinfo:
            raise MissingElementError('fileAuthor')
        assert 'Error: required element fileAuthor is missing.' in str(excinfo.value)

    def test_missing_attribute_error(self):
        """Basic test of MissingAttributeError.
        """
        with pytest.raises(MissingAttributeError) as excinfo:
            raise MissingAttributeError('preferredKey', 'bibliographyLink')
        assert 'Error: required attribute preferredKey of bibliographyLink is missing.' in str(excinfo.value)


class TestFileMetadata(object):
    """
    """
    def test_valid_metadata(self):
        """Ensure valid metadata validates properly.
        """
        root = etree.Element('experiment')
        author = etree.SubElement(root, 'fileAuthor')
        author.text = 'Kyle Niemeyer'
        version = etree.SubElement(root, 'fileVersion')
        major_version = etree.SubElement(version, 'major')
        major_version.text = '1'
        minor_version = etree.SubElement(version, 'minor')
        minor_version.text = '0'

        meta = get_file_metadata(root)
        assert meta['chemked-version'] == __version__
        assert meta['file-authors'][0]['name'] == 'Kyle Niemeyer'
        # ChemKED version will always start at 0
        assert meta['file-version'] == 0

    def test_missing_fileauthor(self):
        """Ensure missing file author raises error.
        """
        root = etree.Element('experiment')
        version = etree.SubElement(root, 'fileVersion')
        major_version = etree.SubElement(version, 'major')
        major_version.text = '1'
        minor_version = etree.SubElement(version, 'minor')
        minor_version.text = '0'

        with pytest.raises(MissingElementError) as excinfo:
            get_file_metadata(root)
        assert 'Error: required element fileAuthor is missing.' in str(excinfo.value)

    def test_blank_fileauthor(self):
        """Ensure blank file author raises error.
        """
        root = etree.Element('experiment')
        author = etree.SubElement(root, 'fileAuthor')
        author.text = ''
        version = etree.SubElement(root, 'fileVersion')
        major_version = etree.SubElement(version, 'major')
        major_version.text = '1'
        minor_version = etree.SubElement(version, 'minor')
        minor_version.text = '0'

        with pytest.raises(MissingElementError) as excinfo:
            get_file_metadata(root)
        assert 'Error: required element fileAuthor is missing' in str(excinfo.value)


class TestGetReference(object):
    """
    """
    @pytest.fixture(scope='function')
    def disable_socket(self):
        """Disables socket to prevent network access.
        """
        old_socket = socket.socket

        def guard(*args, **kwargs):
            raise ConnectionError("No internet")

        socket.socket = guard
        yield
        socket.socket = old_socket

    def test_valid_reference(self):
        """Ensure valid reference reads properly.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')

        ref.set('doi', '10.1016/j.ijhydene.2007.04.008')
        ref.set('preferredKey', 'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond'
                )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)

        m = str(record.pop(UserWarning).message)
        assert m == 'Using DOI to obtain reference information, rather than preferredKey.'

        assert ref['doi'] == '10.1016/j.ijhydene.2007.04.008'
        assert ref['journal'] == 'International Journal of Hydrogen Energy'
        assert ref['year'] == 2007
        assert ref['volume'] == 32
        assert ref['pages'] == '2216-2226'
        assert len(ref['authors']) == 4
        assert {'name': 'N CHAUMEIX'} in ref['authors']
        assert {'name': 'S PICHON'} in ref['authors']
        assert {'name': 'F LAFOSSE'} in ref['authors']
        assert {'name': 'C PAILLARD'} in ref['authors']

    def test_missing_bibliography(self):
        """Test for completely missing bibliography element.
        """
        root = etree.Element('experiment')
        with pytest.raises(MissingElementError) as excinfo:
            get_reference(root)
        assert 'Error: required element bibliographyLink is missing' in str(excinfo.value)

    def test_missing_doi(self):
        """Ensure can handle missing DOI.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')

        ref.set('preferredKey', 'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond'
                )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)

        m = str(record.pop(UserWarning).message)
        assert m == ('Missing doi attribute in bibliographyLink. Setting "detail" key as a '
                     'fallback; please update to the appropriate fields.')

        assert ref['detail'] == ('Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                                 'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                                 'Fig. 12., right, open diamond.'
                                 )

    def test_missing_doi_period_at_end(self):
        """Ensure can handle missing DOI with period at end of reference.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')

        ref.set('preferredKey', 'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond.'
                )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)
        m = str(record.pop(UserWarning).message)
        assert m == ('Missing doi attribute in bibliographyLink. Setting "detail" key as a '
                     'fallback; please update to the appropriate fields.')

        assert ref['detail'] == ('Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                                 'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                                 'Fig. 12., right, open diamond.'
                                 )

    def test_missing_preferredkey(self):
        """Ensure can handle DOI with missing ``preferredKey``.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')

        ref.set('doi', '10.1016/j.ijhydene.2007.04.008')

        ref = get_reference(root)

        assert ref['doi'] == '10.1016/j.ijhydene.2007.04.008'
        assert ref['journal'] == 'International Journal of Hydrogen Energy'
        assert ref['year'] == 2007
        assert ref['volume'] == 32
        assert ref['pages'] == '2216-2226'
        assert len(ref['authors']) == 4
        assert {'name': 'N CHAUMEIX'} in ref['authors']
        assert {'name': 'S PICHON'} in ref['authors']
        assert {'name': 'F LAFOSSE'} in ref['authors']
        assert {'name': 'C PAILLARD'} in ref['authors']

    def test_incorrect_doi(self, capfd):
        """Ensure can handle invalid DOI.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')
        ref.set('doi', '10.1000/invalid.doi')
        ref.set('preferredKey', 'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond'
                )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)

        m = str(record.pop(UserWarning).message)
        assert m == ('Missing doi attribute in bibliographyLink or lookup failed. Setting "detail" '
                     'key as a fallback; please update to the appropriate fields.')

        assert ref['detail'] == (
                'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond.'
                )

    def test_incorrect_doi_period_at_end(self, capfd):
        """Ensure can handle invalid DOI with period at end of reference.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')
        ref.set('doi', '10.1000/invalid.doi')
        ref.set('preferredKey', 'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond.'
                )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)

        m = str(record.pop(UserWarning).message)
        assert m == ('Missing doi attribute in bibliographyLink or lookup failed. Setting "detail" '
                     'key as a fallback; please update to the appropriate fields.')

        assert ref['detail'] == (
                'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond.'
                )

    def test_doi_missing_internet(self, disable_socket):
        """Ensure that DOI validation fails gracefully with no Internet.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')
        ref.set('doi', '10.1016/j.ijhydene.2007.04.008')
        ref.set('preferredKey', 'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond'
                )

        with pytest.warns(UserWarning) as record:
            ref = get_reference(root)
        m = str(record.pop(UserWarning).message)
        assert m == ('Missing doi attribute in bibliographyLink or lookup failed. Setting "detail" '
                     'key as a fallback; please update to the appropriate fields.')

        assert ref['detail'] == ('Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                                 'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                                 'Fig. 12., right, open diamond.'
                                 )

    def test_missing_doi_preferredkey(self):
        """Ensure error if missing both DOI and ``preferredKey``.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')
        ref.set('doi', '10.1000/invalid.doi')

        with pytest.raises(KeywordError) as excinfo:
            ref = get_reference(root)
        assert ('DOI not found and preferredKey attribute not set' in str(excinfo.value))

    def test_doi_missing_preferredkey(self):
        """Ensure error if missing ``preferredKey`` and not found DOI.
        """
        root = etree.Element('experiment')
        etree.SubElement(root, 'bibliographyLink')

        with pytest.raises(MissingAttributeError) as excinfo:
            get_reference(root)
        assert ('Error: required attribute preferredKey of bibliographyLink '
                'is missing.' in str(excinfo.value)
                )

    def test_doi_author_orcid(self):
        """Test proper addition of author ORCID if present.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')
        ref.set('doi', '10.1016/j.cpc.2017.02.004')

        ref = get_reference(root)

        assert ref['doi'] == '10.1016/j.cpc.2017.02.004'
        assert ref['journal'] == 'Computer Physics Communications'
        assert ref['year'] == 2017
        assert ref['volume'] == 215
        assert ref['pages'] == '188-203'
        assert len(ref['authors']) == 3
        assert {'name': 'Kyle E. Niemeyer',
                'ORCID': '0000-0003-4425-7097'
                } in ref['authors']
        assert {'name': 'Nicholas J. Curtis',
                'ORCID': '0000-0002-0303-4711'
                } in ref['authors']
        assert {'name': 'Chih-Jen Sung'} in ref['authors']


class TestGetExperiment(object):
    """
    """
    @pytest.mark.parametrize('apparatus', [
        'shock tube', 'rapid compression machine',
        ])
    def test_proper_experiment_types(self, apparatus):
        """Ensure proper validation of accepted experiment types.
        """
        root = etree.Element('experiment')
        exp = etree.SubElement(root, 'experimentType')
        exp.text = 'Ignition delay measurement'
        app = etree.SubElement(root, 'apparatus')
        kind = etree.SubElement(app, 'kind')
        kind.text = apparatus

        ref = get_experiment_kind(root)
        assert ref['experiment-type'] == 'ignition delay'
        assert ref['apparatus']['kind'] == apparatus

    @pytest.mark.parametrize('experiment_type', [
        'Laminar flame speed measurement',
        'Outlet concentration measurement',
        'Concentration time profile measurement',
        'Jet stirred reactor measurement',
        'Burner stabilized flame speciation measurement',
        ])
    def test_invalid_experiment_types(self, experiment_type):
        """Ensure unsupported types raise correct errors.
        """
        root = etree.Element('experiment')
        exp = etree.SubElement(root, 'experimentType')
        exp.text = experiment_type

        with pytest.raises(NotImplementedError) as excinfo:
            get_experiment_kind(root)
        assert experiment_type + ' not (yet) supported' in str(excinfo.value)

    @pytest.mark.parametrize('apparatus', [
        'perfectly stirred reactor', 'internal combustion engine', 'flow reactor'
        ])
    def test_invalid_apparatus_types(self, apparatus):
        """Ensure unsupported apparatus types raise correct errors.
        """
        root = etree.Element('experiment')
        exp = etree.SubElement(root, 'experimentType')
        exp.text = 'Ignition delay measurement'
        app = etree.SubElement(root, 'apparatus')
        kind = etree.SubElement(app, 'kind')
        kind.text = apparatus

        with pytest.raises(NotImplementedError) as excinfo:
            get_experiment_kind(root)
        assert apparatus + ' experiment not (yet) supported' in str(excinfo.value)

    def test_missing_apparatus_kind(self):
        """Ensure proper error raised if missing apparatus kind.
        """
        root = etree.Element('experiment')
        exp = etree.SubElement(root, 'experimentType')
        exp.text = 'Ignition delay measurement'
        etree.SubElement(root, 'apparatus')

        with pytest.raises(MissingElementError) as excinfo:
            get_experiment_kind(root)
        assert 'Error: required element apparatus/kind is missing.' in str(excinfo.value)

    def test_missing_apparatus(self):
        """Ensure proper error raised if missing apparatus.
        """
        root = etree.Element('experiment')
        exp = etree.SubElement(root, 'experimentType')
        exp.text = 'Ignition delay measurement'

        with pytest.raises(MissingElementError) as excinfo:
            get_experiment_kind(root)
        assert 'Error: required element apparatus/kind is missing.' in str(excinfo.value)


class TestCommonProperties(object):
    """
    """
    @pytest.mark.parametrize('physical_property, value, units', [
        ('pressure', '2.18', 'atm'),
        ('pressure', '700', 'Torr'),
        ('pressure', '700', 'torr'),
        ('pressure', '1', 'bar'),
        ('pressure', '1000', 'mbar'),
        ('temperature', '1000.0', 'K'),
        ('pressure rise', '0.10', '1/ms'),
        ])
    def test_proper_common_properties(self, physical_property, value, units):
        """Ensure proper handling of correct common properties.
        """
        root = etree.Element('experiment')
        properties = etree.SubElement(root, 'commonProperties')

        prop = etree.SubElement(properties, 'property')
        prop.set('name', physical_property)
        prop.set('units', units)
        prop_value = etree.SubElement(prop, 'value')
        prop_value.text = value

        # not sure how else to handle this...
        if units == 'Torr':
            units = 'torr'

        common = get_common_properties(root)
        assert common[physical_property.replace(' ', '-')] == [' '.join([value, units])]

    @pytest.mark.parametrize('physical_property, value, units', [
        ('pressure', '2.18', 'K'),
        ('temperature', '1000.0', 'Pa'),
        ('pressure rise', '0.10', 'ms'),
        ])
    def test_common_property_invalid_units(self, physical_property, value, units):
        """Ensure error raised when improper units given for common properties.
        """
        root = etree.Element('experiment')
        properties = etree.SubElement(root, 'commonProperties')
        prop = etree.SubElement(properties, 'property')
        prop.set('name', physical_property)
        prop.set('units', units)
        prop_value = etree.SubElement(prop, 'value')
        prop_value.text = value

        with pytest.raises(KeywordError) as excinfo:
            get_common_properties(root)
        assert 'Error: units incompatible for property ' + physical_property in str(excinfo.value)

    @pytest.mark.parametrize('composition_type', ['mole fraction', 'mass fraction'])
    def test_proper_common_initial_composition(self, composition_type):
        """Ensure proper handling of initial composition common property.
        """
        root = etree.Element('experiment')
        properties = etree.SubElement(root, 'commonProperties')
        initial_composition = etree.SubElement(properties, 'property')
        initial_composition.set('name', 'initial composition')

        species_refs = [{'name': 'H2', 'inchi': '1S/H2/h1H', 'amount': 0.00444},
                        {'name': 'O2', 'inchi': '1S/O2/c1-2', 'amount': 0.00566},
                        {'name': 'Ar', 'inchi': '1S/Ar', 'amount': 0.9899},
                        ]
        for spec in species_refs:
            component = etree.SubElement(initial_composition, 'component')
            species = etree.SubElement(component, 'speciesLink')
            species.set('preferredKey', spec['name'])
            species.set('InChI', spec['inchi'])
            amount = etree.SubElement(component, 'amount')
            amount.set('units', composition_type)
            amount.text = str(spec['amount'])

        common = get_common_properties(root)
        assert common['composition']['kind'] == composition_type
        assert len(common['composition']['species']) == 3
        for spec_ref, spec in zip(species_refs, common['composition']['species']):
            assert spec['species-name'] == spec_ref['name']
            assert spec['InChI'] == spec_ref['inchi']
            assert spec['amount'] == [spec_ref['amount']]

    def test_common_property_invalid_property(self):
        """Ensure error raised when invalid property given in common properties.
        """
        root = etree.Element('experiment')
        properties = etree.SubElement(root, 'commonProperties')
        prop = etree.SubElement(properties, 'property')
        prop.set('name', 'compression time')

        with pytest.raises(KeywordError) as excinfo:
            get_common_properties(root)
        assert 'Error: Property compression time not supported as common property.' in str(excinfo.value)

    def test_species_missing_inchi(self, capfd):
        """Check for warning when species missing InChI.
        """
        root = etree.Element('experiment')
        properties = etree.SubElement(root, 'commonProperties')
        initial_composition = etree.SubElement(properties, 'property')
        initial_composition.set('name', 'initial composition')

        component = etree.SubElement(initial_composition, 'component')
        species = etree.SubElement(component, 'speciesLink')
        species.set('preferredKey', 'H2')
        amount = etree.SubElement(component, 'amount')
        amount.set('units', 'mole fraction')
        amount.text = '1.0'

        with pytest.warns(UserWarning) as record:
            get_common_properties(root)
        m = str(record.pop(UserWarning).message)
        assert m == 'Missing InChI for species H2'

    def test_inconsistent_composition_type(self):
        """Check for error when inconsistent composition types.
        """
        root = etree.Element('experiment')
        properties = etree.SubElement(root, 'commonProperties')
        initial_composition = etree.SubElement(properties, 'property')
        initial_composition.set('name', 'initial composition')

        component = etree.SubElement(initial_composition, 'component')
        species = etree.SubElement(component, 'speciesLink')
        species.set('preferredKey', 'H2')
        species.set('InChI', '1S/H2/h1H')
        amount = etree.SubElement(component, 'amount')
        amount.set('units', 'mole fraction')
        amount.text = '0.5'

        component = etree.SubElement(initial_composition, 'component')
        species = etree.SubElement(component, 'speciesLink')
        species.set('preferredKey', 'O2')
        species.set('InChI', '1S/O2/c1-2')
        amount = etree.SubElement(component, 'amount')
        amount.set('units', 'mass fraction')
        amount.text = '0.5'

        with pytest.raises(KeywordError) as excinfo:
            get_common_properties(root)
        assert ('Error: composition units mass fraction not consistent '
                'with mole fraction'
                ) in str(excinfo.value)

    def test_common_composition_units_ppm_ppb(self):
        """Test proper handling of common composition unit conversion for ppm and ppb.
        """
        root = etree.Element('experiment')
        properties = etree.SubElement(root, 'commonProperties')
        initial_composition = etree.SubElement(properties, 'property')
        initial_composition.set('name', 'initial composition')

        species_refs = [{'name': 'H2', 'inchi': '1S/H2/h1H',
                         'amount': 100, 'units': 'ppb'
                         },
                        {'name': 'O2', 'inchi': '1S/O2/c1-2',
                         'amount': 10, 'units': 'ppm',
                         },
                        {'name': 'Ar', 'inchi': '1S/Ar',
                         'amount': 0.999985, 'units': 'mole fraction'},
                        ]
        for spec in species_refs:
            component = etree.SubElement(initial_composition, 'component')
            species = etree.SubElement(component, 'speciesLink')
            species.set('preferredKey', spec['name'])
            species.set('InChI', spec['inchi'])
            amount = etree.SubElement(component, 'amount')
            amount.set('units', spec['units'])
            amount.text = str(spec['amount'])

        with pytest.warns(UserWarning) as record:
            common = get_common_properties(root)

        m = str(record.pop(UserWarning).message)
        assert m == 'Assuming molar ppb in composition and converting to mole fraction'
        m = str(record.pop(UserWarning).message)
        assert m == 'Assuming molar ppm in composition and converting to mole fraction'

        assert common['composition']['kind'] == 'mole fraction'
        assert len(common['composition']['species']) == 3
        assert common['composition']['species'][0]['species-name'] == 'H2'
        assert common['composition']['species'][0]['InChI'] == '1S/H2/h1H'
        assert_allclose(common['composition']['species'][0]['amount'], [100.e-9])
        assert common['composition']['species'][1]['species-name'] == 'O2'
        assert common['composition']['species'][1]['InChI'] == '1S/O2/c1-2'
        assert_allclose(common['composition']['species'][1]['amount'], [10.e-6])
        assert common['composition']['species'][2]['species-name'] == 'Ar'
        assert common['composition']['species'][2]['InChI'] == '1S/Ar'
        assert_allclose(common['composition']['species'][2]['amount'], [0.999985])

    def test_common_composition_units_percent(self):
        """Test proper handling of common composition unit conversion for (mole) percent.
        """
        root = etree.Element('experiment')
        properties = etree.SubElement(root, 'commonProperties')
        initial_composition = etree.SubElement(properties, 'property')
        initial_composition.set('name', 'initial composition')

        species_refs = [{'name': 'Ar', 'inchi': '1S/Ar', 'amount': 1.0, 'units': 'percent'}]
        for spec in species_refs:
            component = etree.SubElement(initial_composition, 'component')
            species = etree.SubElement(component, 'speciesLink')
            species.set('preferredKey', spec['name'])
            species.set('InChI', spec['inchi'])
            amount = etree.SubElement(component, 'amount')
            amount.set('units', spec['units'])
            amount.text = str(spec['amount'])

        with pytest.warns(UserWarning) as record:
            common = get_common_properties(root)
        m = str(record.pop(UserWarning).message)
        assert m == 'Assuming percent in composition means mole percent'

        assert common['composition']['kind'] == 'mole percent'
        assert len(common['composition']['species']) == 1
        assert common['composition']['species'][0]['species-name'] == 'Ar'
        assert common['composition']['species'][0]['InChI'] == '1S/Ar'
        assert_allclose(common['composition']['species'][0]['amount'], [1.0])

    def test_common_composition_units_error(self):
        """Test error for inappropriate common composition units.
        """
        root = etree.Element('experiment')
        properties = etree.SubElement(root, 'commonProperties')
        initial_composition = etree.SubElement(properties, 'property')
        initial_composition.set('name', 'initial composition')

        species_refs = [{'name': 'H2', 'inchi': '1S/H2/h1H',
                         'amount': 100, 'units': 'grams'
                         },
                        ]

        for spec in species_refs:
            component = etree.SubElement(initial_composition, 'component')
            species = etree.SubElement(component, 'speciesLink')
            species.set('preferredKey', spec['name'])
            species.set('InChI', spec['inchi'])
            amount = etree.SubElement(component, 'amount')
            amount.set('units', spec['units'])
            amount.text = str(spec['amount'])

        with pytest.raises(KeywordError) as excinfo:
            get_common_properties(root)

        assert ('Composition units need to be one of: mole fraction, '
                'mass fraction, mole percent, percent, ppm, or ppb.') in str(excinfo.value)


class TestIgnitionType(object):
    """
    """
    @pytest.mark.parametrize('ignition_target',
                             ['P', 'T', 'OH', 'OH*', 'CH*', 'CH', 'OHEX', 'CHEX']
                             )
    @pytest.mark.parametrize('ignition_type', ['max', 'd/dt max', '1/2 max', 'min', 'baseline max intercept from d/dt'])
    def test_valid_ignition_types(self, ignition_target, ignition_type):
        """Check for proper parsing of valid ignition types.
        """
        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('target', ignition_target)
        ignition.set('type', ignition_type)

        ignition = get_ignition_type(root)

    def test_missing_attributes(self):
        """Check for error upon missing attributes
        """
        root = etree.Element('experiment')
        with pytest.raises(MissingElementError) as excinfo:
            ignition = get_ignition_type(root)
        assert 'Error: required element ignitionType is missing.' in str(excinfo.value)

        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('target', 'P')
        with pytest.raises(MissingAttributeError) as excinfo:
            ignition = get_ignition_type(root)
        assert 'Error: required attribute type of ignitionType is missing.' in str(excinfo.value)

        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('type', 'max')
        with pytest.raises(MissingAttributeError) as excinfo:
            ignition = get_ignition_type(root)
        assert 'Error: required attribute target of ignitionType is missing.' in str(excinfo.value)

    @pytest.mark.parametrize('ignition_type',
                             ['baseline min intercept from d/dt',
                              'concentration', 'relative concentration'
                              ])
    def test_unsupported_ignition_types(self, ignition_type):
        """Check error returned for unsupported/invalid ignition types.
        """
        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('target', 'P')
        ignition.set('type', ignition_type)

        with pytest.raises(KeywordError) as excinfo:
            ignition = get_ignition_type(root)
        assert 'Error: ' + ignition_type + ' not valid ignition type' in str(excinfo.value)

    @pytest.mark.parametrize('ignition_target', ['O2', 'CO', 'density'])
    def test_unsupported_ignition_targets(self, ignition_target):
        """Check error returned for unsupported/invalid ignition targets.
        """
        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('target', ignition_target)
        ignition.set('type', 'max')

        with pytest.raises(KeywordError) as excinfo:
            ignition = get_ignition_type(root)
        assert ('Error: ' + ignition_target.upper() + ' not valid ignition target'
                in str(excinfo.value)
                )

    def test_multiple_targets(self):
        """Check for error with multiple ignition targets.
        """
        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('target', 'OH;CH')
        ignition.set('type', 'max')

        with pytest.raises(NotImplementedError) as excinfo:
            ignition = get_ignition_type(root)
        assert 'Multiple ignition targets not supported.' in str(excinfo.value)


class TestGetDatapoints(object):
    """
    """
    def test_valid_datapoints_single_datagroup(self):
        """Test valid parsing of datapoints when in a single dataGroup.
        """
        root = etree.Element('experiment')
        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'ignition delay')
        prop.set('units', 'us')

        num_points = 10
        temps = numpy.random.uniform(low=300.0, high=1000.0, size=(num_points,))
        ignition_delays = numpy.random.uniform(low=100., high=700., size=(num_points,))

        for temp, ignition_delay in zip(temps, ignition_delays):
            datapoint = etree.SubElement(datagroup, 'dataPoint')
            x1 = etree.SubElement(datapoint, 'x1')
            x1.text = str(temp)
            x2 = etree.SubElement(datapoint, 'x2')
            x2.text = str(ignition_delay)

        datapoints = get_datapoints(root)
        assert len(datapoints) == num_points
        for datapoint, temp, ignition_delay in zip(datapoints, temps, ignition_delays):
            assert datapoint['temperature'] == [str(temp) + ' K']
            assert datapoint['ignition-delay'] == [str(ignition_delay) + ' us']

    def test_valid_datapoints_two_datagroup(self):
        """Test valid parsing of datapoints when in a two dataGroups.
        """
        root = etree.Element('experiment')
        apparatus = etree.SubElement(root, 'apparatus')
        kind = etree.SubElement(apparatus, 'kind')
        kind.text = 'rapid compression machine'

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'ignition delay')
        prop.set('units', 'us')

        temp = numpy.random.uniform(low=300.0, high=1000.0)
        ignition_delay = numpy.random.uniform(low=100., high=700.)
        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(temp)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(ignition_delay)

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x4')
        prop.set('name', 'time')
        prop.set('units', 's')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x5')
        prop.set('name', 'volume')
        prop.set('units', 'cm3')

        num_points = 100
        times = numpy.linspace(0., 10.e-2, num_points)
        volumes = numpy.cos(times * 20. * numpy.pi)
        for time, volume in zip(times, volumes):
            datapoint = etree.SubElement(datagroup, 'dataPoint')
            x1 = etree.SubElement(datapoint, 'x4')
            x1.text = str(time)
            x2 = etree.SubElement(datapoint, 'x5')
            x2.text = str(volume)

        datapoints = get_datapoints(root)

        assert len(datapoints) == 1
        datapoint = datapoints[0]
        assert datapoint['temperature'] == [str(temp) + ' K']
        assert datapoint['ignition-delay'] == [str(ignition_delay) + ' us']

        volume_history = datapoint['time-histories'][0]
        assert len(volume_history['values']) == num_points
        assert volume_history['time']['units'] == 's'
        assert volume_history['time']['column'] == 0
        assert volume_history['quantity']['units'] == 'cm3'
        assert volume_history['quantity']['column'] == 1
        for datapoint, time, volume in zip(volume_history['values'], times, volumes):
            assert datapoint == [float(str(time)), float(str(volume))]

    def test_missing_datagroup_property_datapoint(self):
        """Raise error when missing a dataGroup, property, or dataPoint.
        """
        root = etree.Element('experiment')
        with pytest.raises(MissingElementError) as excinfo:
            get_datapoints(root)
        assert 'Error: required element dataGroup is missing.' in str(excinfo.value)

        datagroup = etree.SubElement(root, 'dataGroup')
        with pytest.raises(MissingElementError) as excinfo:
            get_datapoints(root)
        assert 'Error: required element property is missing.' in str(excinfo.value)

        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')

        with pytest.raises(MissingElementError) as excinfo:
            get_datapoints(root)
        assert 'Error: required element dataPoint is missing.' in str(excinfo.value)

    def test_datapoint_invalid_property(self):
        """Raise error when invalid property for a ``dataPoint``.
        """
        root = etree.Element('experiment')
        exp = etree.SubElement(root, 'experimentType')
        exp.text = 'Ignition delay measurement'
        app = etree.SubElement(root, 'apparatus')
        kind = etree.SubElement(app, 'kind')
        kind.text = 'shock tube'

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'compression time')
        prop.set('units', 'ms')
        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(30.0)

        datagroup = etree.SubElement(root, 'dataGroup')
        with pytest.raises(KeyError) as excinfo:
            get_datapoints(root)
        assert 'compression time not valid dataPoint property' in str(excinfo.value)

    def test_datapoint_extra_value(self):
        """Raise error when value without associated property definition
        """
        root = etree.Element('experiment')
        exp = etree.SubElement(root, 'experimentType')
        exp.text = 'Ignition delay measurement'
        app = etree.SubElement(root, 'apparatus')
        kind = etree.SubElement(app, 'kind')
        kind.text = 'shock tube'

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(100.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert 'value missing from properties: x2' in str(excinfo.value)

    def test_time_history_extra_property(self):
        """Ensure error when extra property in volume history dataGroup.
        """
        root = etree.Element('experiment')
        apparatus = etree.SubElement(root, 'apparatus')
        kind = etree.SubElement(apparatus, 'kind')
        kind.text = 'rapid compression machine'

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'ignition delay')
        prop.set('units', 'us')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(100.0)

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x3')
        prop.set('name', 'time')
        prop.set('units', 's')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x4')
        prop.set('name', 'volume')
        prop.set('units', 'cm3')

        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x5')
        prop.set('name', 'not allowed property')
        prop.set('units', 'Pa')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x3 = etree.SubElement(datapoint, 'x3')
        x3.text = str(0.0)
        x4 = etree.SubElement(datapoint, 'x4')
        x4.text = str(50.0)
        x5 = etree.SubElement(datapoint, 'x5')
        x5.text = str(101325.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert ('Only volume, temperature, pressure, and time are allowed in a time-history '
                'dataGroup.') in str(excinfo.value)

        # remove bad property description, but retain bad extra dataPoint value
        datagroup.remove(prop)
        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert ('Value tag {} not found in dataGroup tags: {}'.format('x5', ['x4'])
                in str(excinfo.value))

    def test_volume_history_missing_property(self):
        """Ensure error when missing property in volume history dataGroup.
        """
        root = etree.Element('experiment')
        apparatus = etree.SubElement(root, 'apparatus')
        kind = etree.SubElement(apparatus, 'kind')
        kind.text = 'rapid compression machine'

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'ignition delay')
        prop.set('units', 'us')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(100.0)

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x3')
        prop.set('name', 'time')
        prop.set('units', 's')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x3 = etree.SubElement(datapoint, 'x3')
        x3.text = str(0.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert ('Both time and quantity properties required for time-history.' in str(excinfo.value))

        # try the same with volume, and time missing
        datagroup.remove(prop)
        datagroup.remove(datapoint)
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x4')
        prop.set('name', 'volume')
        prop.set('units', 'cm3')
        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x3 = etree.SubElement(datapoint, 'x4')
        x3.text = str(50.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert ('Both time and quantity properties required for time-history.' in str(excinfo.value))

    def test_volume_history_missing_value(self):
        """Ensure error when missing value in volume history dataGroup.
        """
        root = etree.Element('experiment')
        apparatus = etree.SubElement(root, 'apparatus')
        kind = etree.SubElement(apparatus, 'kind')
        kind.text = 'rapid compression machine'

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'ignition delay')
        prop.set('units', 'us')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(100.0)

        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x3')
        prop.set('name', 'time')
        prop.set('units', 's')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x4')
        prop.set('name', 'volume')
        prop.set('units', 'cm3')

        # Have time, but missing volume
        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x3 = etree.SubElement(datapoint, 'x3')
        x3.text = str(0.0)
        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert ('Both time and quantity values required in each time-history dataPoint.'
                in str(excinfo.value))

        # try again with volume, but missing time
        datapoint.remove(x3)
        x4 = etree.SubElement(datapoint, 'x4')
        x4.text = str(50.0)
        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert ('Both time and quantity values required in each time-history dataPoint.'
                in str(excinfo.value))

    @pytest.mark.parametrize('type, value', [
        ('mole fraction', 1.0),
        ('mass fraction', 1.0),
        ('mole percent', 100.0),
        ])
    @pytest.mark.filterwarnings('ignore:Missing InChI for species H2')
    def test_datapoints_composition(self, type, value):
        """Test valid parsing of datapoints with composition.
        """
        root = etree.Element('experiment')
        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'ignition delay')
        prop.set('units', 'us')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x3')
        prop.set('name', 'composition')
        prop.set('units', type)
        specieslink = etree.SubElement(prop, 'speciesLink')
        specieslink.set('preferredKey', 'H2')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(100.0)
        x3 = etree.SubElement(datapoint, 'x3')
        x3.text = str(value)

        datapoints = get_datapoints(root)
        assert len(datapoints) == 1
        datapoint = datapoints[0]
        assert datapoint['temperature'] == [str(1000.0) + ' K']
        assert datapoint['ignition-delay'] == [str(100.0) + ' us']
        assert datapoint['composition']['kind'] == type
        assert datapoint['composition']['species'][0] == {'amount': [value],
                                                          'species-name': 'H2',
                                                          'InChI': None
                                                          }

    @pytest.mark.parametrize('kind, value', [
        ('percent', 100.0),
        ('ppm', 1.0),
        ('ppb', 1.0),
        ])
    def test_datapoints_composition_warning(self, kind, value):
        """Test valid parsing of datapoints with composition with warnings.
        """
        root = etree.Element('experiment')
        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'ignition delay')
        prop.set('units', 'us')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x3')
        prop.set('name', 'composition')
        prop.set('units', kind)
        specieslink = etree.SubElement(prop, 'speciesLink')
        specieslink.set('preferredKey', 'H2')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(100.0)
        x3 = etree.SubElement(datapoint, 'x3')
        x3.text = str(value)

        with pytest.warns(UserWarning) as record:
            datapoints = get_datapoints(root)
        m = str(record.pop(UserWarning).message)
        assert m == 'Missing InChI for species H2'
        m = str(record.pop(UserWarning).message)
        if kind == 'percent':
            assert m == 'Assuming percent in composition means mole percent'
            kind = 'mole percent'
        elif kind == 'ppm':
            assert m == 'Assuming molar ppm in composition and converting to mole fraction'
            kind = 'mole fraction'
            value *= 1e-6
        elif kind == 'ppb':
            assert m == 'Assuming molar ppb in composition and converting to mole fraction'
            kind = 'mole fraction'
            value *= 1e-9

        assert len(datapoints) == 1
        datapoint = datapoints[0]
        assert datapoint['temperature'] == [str(1000.0) + ' K']
        assert datapoint['ignition-delay'] == [str(100.0) + ' us']
        assert datapoint['composition']['kind'] == kind
        assert datapoint['composition']['species'][0] == {'amount': [value],
                                                          'species-name': 'H2',
                                                          'InChI': None
                                                          }

    def test_datapoints_composition_error(self):
        """Test valid parsing of datapoints with improper unit error.
        """
        root = etree.Element('experiment')
        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'ignition delay')
        prop.set('units', 'us')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x3')
        prop.set('name', 'composition')
        prop.set('units', 'grams')
        specieslink = etree.SubElement(prop, 'speciesLink')
        specieslink.set('preferredKey', 'H2')
        specieslink.set('InChI', '1S/H2/h1H')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(100.0)
        x3 = etree.SubElement(datapoint, 'x3')
        x3.text = str(10.0)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert ('Error: composition units need to be one of: mole fraction, '
                'mass fraction, mole percent, percent, ppm, or ppb.'
                ) in str(excinfo.value)

    def test_datapoints_inconsistent_composition_error(self):
        """Test error raised for datapoint with inconsistent composition type.
        """
        root = etree.Element('experiment')
        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'temperature')
        prop.set('units', 'K')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'ignition delay')
        prop.set('units', 'us')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x3')
        prop.set('name', 'composition')
        prop.set('units', 'mass fraction')
        specieslink = etree.SubElement(prop, 'speciesLink')
        specieslink.set('preferredKey', 'H2')
        specieslink.set('InChI', '1S/H2/h1H')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x4')
        prop.set('name', 'composition')
        prop.set('units', 'mole fraction')
        specieslink = etree.SubElement(prop, 'speciesLink')
        specieslink.set('preferredKey', 'O2')
        specieslink.set('InChI', '1S/O2/c1-2')

        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(1000.0)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(100.0)
        x3 = etree.SubElement(datapoint, 'x3')
        x3.text = str(0.5)
        x3 = etree.SubElement(datapoint, 'x4')
        x3.text = str(0.5)

        with pytest.raises(KeywordError) as excinfo:
            get_datapoints(root)
        assert ('Error: composition units mole fraction not consistent with '
                'mass fraction'
                ) in str(excinfo.value)


class TestConvertReSpecTh(object):
    """
    """
    @pytest.mark.parametrize('filename_xml', ['testfile_st.xml', 'testfile_rcm.xml'])
    @pytest.mark.filterwarnings('ignore:Using DOI')
    def test_valid_conversion(self, filename_xml):
        """Test proper conversion of ReSpecTh files.
        """
        file_path = os.path.join(filename_xml)
        filename = pkg_resources.resource_filename(__name__, file_path)
        file_author = 'Kyle Niemeyer'
        file_author_orcid = '0000-0003-4425-7097'
        # Skip all the validation because we know the test files are correct and we're not
        # testing the validation methods here
        properties = ReSpecTh_to_ChemKED(filename, file_author, file_author_orcid, validate=False)
        c = ChemKED(dict_input=properties, skip_validation=True)

        # compare with ChemKED file of same experiment
        file_path = os.path.join(os.path.splitext(filename_xml)[0] + '.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        c_true = ChemKED(yaml_file=filename, skip_validation=True)

        assert c.file_authors[1]['name'] == file_author
        assert c.file_authors[1]['ORCID'] == file_author_orcid

        assert c.reference.detail == 'Converted from ReSpecTh XML file {}'.format(filename_xml)

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)

    @pytest.mark.filterwarnings('ignore:Using DOI')
    def test_error_rcm_pressurerise(self):
        """Test for appropriate error if RCM file has pressure rise.
        """
        file_path = os.path.join('testfile_rcm.xml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        # add pressure rise to common properties
        tree = etree.parse(filename)
        root = tree.getroot()
        properties = root.find('commonProperties')
        prop = etree.SubElement(properties, 'property')
        prop.set('name', 'pressure rise')
        prop.set('units', '1/ms')
        prop_value = etree.SubElement(prop, 'value')
        prop_value.text = '0.10'

        # write new file, and try to load
        et = etree.ElementTree(root)
        with TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, 'test.xml')
            et.write(filename, encoding='utf-8', xml_declaration=True)

            with pytest.raises(KeywordError) as excinfo:
                ReSpecTh_to_ChemKED(filename)
            assert 'Pressure rise cannot be defined for RCM.' in str(excinfo.value)

    @pytest.mark.filterwarnings('ignore:Using DOI')
    def test_error_st_volumehistory(self):
        """Test for appropriate error if shock tube file has volume history.
        """
        file_path = os.path.join('testfile_st.xml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        tree = etree.parse(filename)
        root = tree.getroot()
        datagroup = etree.SubElement(root, 'dataGroup')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x1')
        prop.set('name', 'time')
        prop.set('units', 's')
        prop = etree.SubElement(datagroup, 'property')
        prop.set('id', 'x2')
        prop.set('name', 'volume')
        prop.set('units', 'cm3')
        datapoint = etree.SubElement(datagroup, 'dataPoint')
        x1 = etree.SubElement(datapoint, 'x1')
        x1.text = str(0.0)
        x2 = etree.SubElement(datapoint, 'x2')
        x2.text = str(10.0)

        # write new file, and try to load
        et = etree.ElementTree(root)
        with TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, 'test.xml')
            et.write(filename, encoding='utf-8', xml_declaration=True)

            with pytest.raises(KeywordError) as excinfo:
                ReSpecTh_to_ChemKED(filename)
            assert 'Volume history cannot be defined for shock tube.' in str(excinfo.value)

    @pytest.mark.filterwarnings('ignore:Using DOI')
    def test_author_orcid_no_name(self):
        """Test that passing an ORCID to the conversion without a name raises an error
        """
        file_path = os.path.join('testfile_st.xml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        file_author_orcid = '0000-0003-4425-7097'
        # Skip all the validation because we know the test files are correct and we're not
        # testing the validation methods here
        with pytest.raises(KeywordError) as e:
            ReSpecTh_to_ChemKED(filename, file_author_orcid=file_author_orcid)
        assert 'If file_author_orcid is specified, file_author must be as well' in str(e.value)

    @pytest.mark.filterwarnings('ignore:Using DOI')
    def test_file_author_only(self):
        """Test that passing the file author only works properly
        """
        file_path = os.path.join('testfile_st.xml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        file_author = 'Kyle Niemeyer'
        # Skip all the validation because we know the test files are correct and we're not
        # testing the validation methods here
        properties = ReSpecTh_to_ChemKED(filename, file_author, validate=False)
        c = ChemKED(dict_input=properties, skip_validation=True)

        assert c.file_authors[1]['name'] == file_author
        assert c.file_authors[1].get('ORCID', None) is None


class TestConverterMain(object):
    """
    """
    def test_conversion_main_xml_to_yaml(self):
        """Test detection in converter for xml->yaml
        """
        file_path = os.path.join('testfile_st.xml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        file_author = 'Kyle E Niemeyer'
        file_author_orcid = '0000-0003-4425-7097'

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.yaml')
            with pytest.warns(UserWarning) as record:
                main(['-i', filename, '-o', newfile, '-fa', file_author, '-fo', file_author_orcid])
            c = ChemKED(yaml_file=newfile)

        m = str(record.pop(UserWarning).message)
        assert m == 'Using DOI to obtain reference information, rather than preferredKey.'
        true_yaml = pkg_resources.resource_filename(__name__, os.path.join('testfile_st.yaml'))
        c_true = ChemKED(yaml_file=true_yaml)

        assert c.file_authors[0]['name'] == c_true.file_authors[0]['name']
        assert c.file_authors[1]['name'] == file_author
        assert c.file_authors[1]['ORCID'] == file_author_orcid

        assert c.reference.detail == 'Converted from ReSpecTh XML file {}'.format(file_path)

        assert c.apparatus.kind == c_true.apparatus.kind
        assert c.experiment_type == c_true.experiment_type
        assert c.reference.doi == c_true.reference.doi
        assert len(c.datapoints) == len(c_true.datapoints)

    def test_conversion_main_yaml_to_xml(self):
        """Test detection in converter for yaml->xml
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)
        fa_name = 'Kyle Niemeyer'
        fa_orcid = '0000-0003-4425-7097'

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            main(['-i', filename, '-o', newfile, '-fa', fa_name, '-fo', fa_orcid])

            assert os.path.exists(newfile)

    def test_conversion_respth2ck_default_output(self):
        """Test respth2ck converter when used via command-line arguments.
        """
        file_path = os.path.join('testfile_st.xml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with TemporaryDirectory() as temp_dir:
            xml_file = copy(filename, temp_dir)
            with pytest.warns(UserWarning) as record:
                respth2ck(['-i', xml_file])

            newfile = os.path.join(os.path.splitext(xml_file)[0] + '.yaml')
            assert os.path.exists(newfile)

        m = str(record.pop(UserWarning).message)
        assert m == 'Using DOI to obtain reference information, rather than preferredKey.'

    def test_conversion_respth2ck_with_output(self):
        """Test respth2ck converter when used via command-line arguments.
        """
        file_path = os.path.join('testfile_st.xml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.yaml')
            with pytest.warns(UserWarning) as record:
                respth2ck(['-i', filename, '-o', newfile])

            assert os.path.exists(newfile)

        m = str(record.pop(UserWarning).message)
        assert m == 'Using DOI to obtain reference information, rather than preferredKey.'

    def test_conversion_ck2respth(self):
        """Test ck2respth converter when used via command-line arguments.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with TemporaryDirectory() as temp_dir:
            newfile = os.path.join(temp_dir, 'test.xml')
            ck2respth(['-i', filename, '-o', newfile])

            assert os.path.exists(newfile)

    def test_conversion_invalid_xml_xml(self):
        """Test converter main raises errors when two xml files are passed.
        """
        file_path = os.path.join('testfile_st.xml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with pytest.raises(KeywordError) as excinfo:
            main(['-i', filename, '-o', 'test.xml'])
        assert 'Cannot convert .xml to .xml' in str(excinfo.value)

    def test_conversion_invalid_yaml_yaml(self):
        """Test converter main raises errors when two yaml files are passed.
        """
        file_path = os.path.join('testfile_st.yaml')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with pytest.raises(KeywordError) as excinfo:
            main(['-i', filename, '-o', 'test.yaml'])
        assert 'Cannot convert .yaml to .yaml' in str(excinfo.value)

    def test_conversion_invalid_file_type(self):
        """Test converter main raises errors when an invalid file extension is passed.
        """
        file_path = os.path.join('dataframe_st.csv')
        filename = pkg_resources.resource_filename(__name__, file_path)

        with pytest.raises(KeywordError) as excinfo:
            main(['-i', filename, '-o', 'test.py'])
        assert 'Input/output args need to be .xml/.yaml' in str(excinfo.value)
