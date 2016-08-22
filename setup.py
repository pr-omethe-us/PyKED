#!/usr/bin/env python
# -*- coding: utf-8 -*-

from setuptools import setup
# To use a consistent encoding
from codecs import open

with open('chemked/_version.py') as version_file:
    exec(version_file.read())

with open('README.md') as readme_file:
    readme = readme_file.read()

with open('CHANGELOG.md') as changelog_file:
    changelog = changelog_file.read()

requirements = ['ruamel.yaml>=0.12.5',
                'cerberus>=0.9.2',
                'pint>=0.7.2',
                'pytest>=2.9.2',
                'numpy>=1.11.0',
                ]

test_requirements = [# TODO: put package test requirements here
                     ]

setup(
    name='chemked',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version=__version__,

    description='Package for manipulating Chemical Kinetics Experimental Data (ChemKED) files.',
    long_description=readme + '\n\n' + changelog,
    author='Kyle Niemeyer',
    author_email='kyle.niemeyer@gmail.com',
    url='https://github.com/Niemeyer-Research-Group/ChemKED',
    packages=['chemked',],
    package_dir={'chemked': 'chemked'},
    include_package_data=True,
    install_requires=requirements,
    license='MIT license',
    zip_safe=False,
    keywords=['chemical kinetics',],
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        ],
    test_suite='tests',
    tests_require=test_requirements
)
