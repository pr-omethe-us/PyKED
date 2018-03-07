.. Installation documentation

Installation
============

Stable
------

PyKED is available for Python 3.5 and 3.6 on Linux, macOS, and Windows via ``conda`` and ``pip``.
For ``conda`` installation, use the ``pr-omethe-us`` channel::

    conda install -c pr-omethe-us pyked

Note that you might need to include the ``conda-forge`` channel by editing your conda
configuration::

    conda config --append channels conda-forge
    conda install -c pr-omethe-us pyked

You can also install with ``pip``::

    pip install pyked

Development
-----------

PyKED can be installed from source by cloning the git repository and changing into that directory::

    git clone https://github.com/pr-omethe-us/PyKED
    cd PyKED

Then run::

    conda develop .

if you're using ``conda`` (you may need to install ``conda-build`` first). To uninstall, run::

    conda develop . --uninstall

Note that this doesn't install the standalone converter scripts. With ``pip``, installing
is done by::

    pip install -e .

To uninstall with ``pip``::

    pip uninstall pyked

``pip`` does install the standalone scripts.
