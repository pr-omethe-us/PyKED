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
                                
