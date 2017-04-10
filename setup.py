from setuptools import setup
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, 'pyked', '_version.py')) as version_file:
    exec(version_file.read())

with open(path.join(here, 'README.md')) as readme_file:
    readme = readme_file.read()

with open(path.join(here, 'CHANGELOG.md')) as changelog_file:
    changelog = changelog_file.read()

with open(path.join(here, 'CITATION.md')) as citation_file:
    citation = citation_file.read()

desc = readme + '\n\n' + changelog + '\n\n' + citation
try:
    import pypandoc
    long_description = pypandoc.convert_text(desc, 'rst', format='md')
except ImportError:
    long_description = desc

setup(
    name='pyked',
    version=__version__,
    description='Package for manipulating Chemical Kinetics Experimental Data (ChemKED) files.',
    long_description=long_description,
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
        'orcid>=0.7.0,<1.0',
        'uncertainties>=3.0.1',
    ],
    license='BSD-3-Clause',
    zip_safe=False,
    keywords=['chemical kinetics'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Intended Audience :: Science/Research',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Topic :: Scientific/Engineering :: Chemistry',
    ],
    test_suite='tests',
    tests_require=[
        'pytest>=3.0.1',
        'pytest-cov',
    ],
)
