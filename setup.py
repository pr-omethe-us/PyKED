#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup
# To use a consistent encoding
from codecs import open

with open('pyked/_version.py') as version_file:
    exec(version_file.read())

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('CHANGELOG.md') as changelog_file:
    changelog = changelog_file.read()

setup(
    name='pyked',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version=__version__,

    description='Package for manipulating Chemical Kinetics Experimental Data (ChemKED) files.',
    long_description=readme + '\n\n' + changelog,
    author='Kyle Niemeyer',
    author_email='kyle.niemeyer@gmail.com',
    url='https://github.com/pr-omethe-us/PyKED',
    packages=['pyked', 'pyked.tests'],
    package_dir={'pyked': 'pyked'},
    include_package_data=True,
    package_data={'pyked': ['chemked_schema.yaml', 'tests/*.yaml', 'tests/dataframe_st.csv']},

    install_requires=[
        'pyyaml>=3.12,<4.0',
        'cerberus>=1.0.0',
        'pint>=0.7.2',
        'numpy>=1.11.0',
        'habanero>=0.2.6',
        'orcid>=0.7.0',
        'uncertainties>=3.0.1',
    ],

    license='BSD-3-Clause',
    zip_safe=False,
    keywords=['chemical kinetics'],
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
    ],

    test_suite='tests',
    tests_require=[
        'pytest>=3.0.1',
        'pytest-cov',
    ],
)
