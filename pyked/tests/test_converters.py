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

try:
    from lxml import etree
except ImportError:
    try:
        import xml.etree.cElementTree as etree
    except ImportError:
        try:
            import xml.etree.ElementTree as etree
        except ImportError:
            print("Failed to import ElementTree from any known place")
            raise

# Local imports
from ..converters import (get_file_metadata, get_reference, get_experiment_kind,
                          get_common_properties, get_ignition_type, get_datapoints,
                          read_experiment, convert_ReSpecTh_to_ChemKED
                          )
from .._version import __version__

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
        assert meta['file-author']['name'] == 'Kyle Niemeyer'
        assert meta['file-version'] == int(float(1.0))

    def test_missing_fileauthor(self):
        """Ensure missing file author raises error.
        """
        root = etree.Element('experiment')
        version = etree.SubElement(root, 'fileVersion')
        major_version = etree.SubElement(version, 'major')
        major_version.text = '1'
        minor_version = etree.SubElement(version, 'minor')
        minor_version.text = '0'

        with pytest.raises(AttributeError) as excinfo:
            meta = get_file_metadata(root)

        assert 'Error: no fileAuthor given' in str(excinfo.value)

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

        with pytest.raises(AttributeError) as excinfo:
            meta = get_file_metadata(root)

        assert 'Error: no fileAuthor given' in str(excinfo.value)

    def test_missing_version(self, capfd):
        """Ensure missing version raises warning.
        """
        root = etree.Element('experiment')
        author = etree.SubElement(root, 'fileAuthor')
        author.text = 'Kyle Niemeyer'

        meta = get_file_metadata(root)

        out, err = capfd.readouterr()
        assert out == ('Warning: no fileVersion given\n')

    def test_missing_version_majorminor(self, capfd):
        """Ensure missing version major/minor raises error.
        """
        root = etree.Element('experiment')
        author = etree.SubElement(root, 'fileAuthor')
        author.text = 'Kyle Niemeyer'
        version = etree.SubElement(root, 'fileVersion')
        major_version = etree.SubElement(version, 'major')
        major_version.text = '1'

        with pytest.raises(AttributeError):
            meta = get_file_metadata(root)

        out, err = capfd.readouterr()
        assert out == ('Error: missing fileVersion major/minor\n')


class TestGetReference(object):
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

    def test_missing_bibliography(self):
        """Test for completely missing bibliography element.
        """
        root = etree.Element('experiment')
        with pytest.raises(AttributeError) as excinfo:
            ref = get_reference(root)
        assert 'Error: missing bibliographyLink' in str(excinfo.value)

    def test_missing_doi(self, capfd):
        """Ensure can handle missing DOI.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')

        ref.set('preferredKey', 'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond'
                )

        ref = get_reference(root)

        out, err = capfd.readouterr()
        assert out == ('Warning: missing doi attribute in bibliographyLink\n'
                       'Setting "detail" key as a fallback; please update.\n'
                       )
        assert ref['detail'] == ('Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                                 'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                                 'Fig. 12., right, open diamond.'
                                 )

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

        ref = get_reference(root)

        out, err = capfd.readouterr()
        assert out == ('DOI not found\n'
                       'Warning: missing doi attribute in bibliographyLink\n'
                       'Setting "detail" key as a fallback; please update.\n'
                       )
        assert ref['detail'] == ('Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                                 'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                                 'Fig. 12., right, open diamond.'
                                 )

    def test_doi_missing_internet(self, capfd, disable_socket):
        """Ensure that DOI validation fails gracefully with no Internet.
        """
        root = etree.Element('experiment')
        ref = etree.SubElement(root, 'bibliographyLink')
        ref.set('doi', '10.1016/j.ijhydene.2007.04.008')
        ref.set('preferredKey', 'Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                'Fig. 12., right, open diamond'
                )

        ref = get_reference(root)
        with pytest.warns(UserWarning) as w:
            ref = get_reference(root)

        out, err = capfd.readouterr()
        assert w[0].message.args[0] == 'network not available, DOI not validated.'
        assert ('Warning: missing doi attribute in bibliographyLink\n'
                'Setting "detail" key as a fallback; please update.\n'
                ) in out
        assert ref['detail'] == ('Chaumeix, N., Pichon, S., Lafosse, F., Paillard, C.-E., '
                                 'International Journal of Hydrogen Energy, 2007, (32) 2216-2226, '
                                 'Fig. 12., right, open diamond.'
                                 )

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

        with pytest.raises(KeyError) as excinfo:
            ref = get_experiment_kind(root)
        assert 'experimentType not ignition delay measurement' in str(excinfo.value)

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
            ref = get_experiment_kind(root)
        assert apparatus + ' experiment not (yet) supported' in str(excinfo.value)

    def test_missing_apparatus(self):
        """Ensure proper error raised if missing apparatus.
        """
        # apparatus, but no kind
        root = etree.Element('experiment')
        exp = etree.SubElement(root, 'experimentType')
        exp.text = 'Ignition delay measurement'
        app = etree.SubElement(root, 'apparatus')

        with pytest.raises(AttributeError) as excinfo:
            ref = get_experiment_kind(root)
        assert 'Missing apparatus/kind' in str(excinfo.value)

        # missing apparatus altogether
        root = etree.Element('experiment')
        exp = etree.SubElement(root, 'experimentType')
        exp.text = 'Ignition delay measurement'

        with pytest.raises(AttributeError) as excinfo:
            ref = get_experiment_kind(root)
        assert 'Missing apparatus/kind' in str(excinfo.value)


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
        ('compression time', '38.0', 'ms'),
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
        ('compression time', '38.0', '1/ms'),
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

        with pytest.raises(KeyError) as excinfo:
            common = get_common_properties(root)
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
        prop.set('name', 'ignition delay')

        with pytest.raises(KeyError) as excinfo:
            common = get_common_properties(root)
        assert 'Property ignition delay not supported as common property.' in str(excinfo.value)

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

        common = get_common_properties(root)
        out, err = capfd.readouterr()
        assert out == 'Warning: missing InChI for species H2\n'

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

        with pytest.raises(KeyError) as excinfo:
            common = get_common_properties(root)
        assert 'inconsistent initial composition units' in str(excinfo.value)


class TestIgnitionType(object):
    """
    """
    @pytest.mark.parametrize('ignition_target',
                             ['P', 'T', 'OH', 'OH*', 'CH*', 'CH', 'OHEX', 'CHEX']
                             )
    @pytest.mark.parametrize('ignition_type', ['max', 'd/dt max', '1/2 max', 'min'])
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
        with pytest.raises(AttributeError) as excinfo:
            ignition = get_ignition_type(root)
        assert 'missing ignitionType' in str(excinfo.value)

        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('target', 'P')
        with pytest.raises(AttributeError) as excinfo:
            ignition = get_ignition_type(root)
        assert 'missing ignitionType/type' in str(excinfo.value)

        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('type', 'max')
        with pytest.raises(AttributeError) as excinfo:
            ignition = get_ignition_type(root)
        assert 'missing ignitionType/target' in str(excinfo.value)

    @pytest.mark.parametrize('ignition_type',
                             ['baseline max intercept from d/dt',
                              'baseline min intercept from d/dt',
                              'concentration', 'relative concentration'
                              ])
    def test_unsupported_ignition_types(self, ignition_type):
        """Check error returned for unsupported/invalid ignition types.
        """

        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('target', 'P')
        ignition.set('type', ignition_type)

        with pytest.raises(KeyError) as excinfo:
            ignition = get_ignition_type(root)
        assert ignition_type + ' not valid ignition type' in str(excinfo.value)

    @pytest.mark.parametrize('ignition_target', ['O2', 'CO', 'density'])
    def test_unsupported_ignition_types(self, ignition_target):
        """Check error returned for unsupported/invalid ignition targets.
        """

        root = etree.Element('experiment')
        ignition = etree.SubElement(root, 'ignitionType')
        ignition.set('target', ignition_target)
        ignition.set('type', 'max')

        with pytest.raises(KeyError) as excinfo:
            ignition = get_ignition_type(root)
        assert ignition_target.upper() + ' not valid ignition target' in str(excinfo.value)

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
