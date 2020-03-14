Actilectrum - Lightweight Actinium client
==========================================

Actilectrum is a port of Actilectrum, the Bitcoin wallet, to Actinium.

::

  Licence: MIT Licence
  Original Author: Thomas Voegtlin
  Port Maintainer: Harris Brakmic
  Language: Python (>= 3.6)
  Homepage: https://actilectrum.org/






Getting started
===============

(*If you've come here looking to simply run Actilectrum,* `you may download it here`_.)

.. _you may download it here: https://actilectrum.org

Actilectrum itself is pure Python, and so are most of the required dependencies,
but not everything. The following sections describe how to run from source, but here
is a TL;DR::

    sudo apt-get install libsecp256k1-0
    python3 -m pip install --user .[gui,crypto]


Not pure-python dependencies
----------------------------

If you want to use the Qt interface, install the Qt dependencies::

    sudo apt-get install python3-pyqt5

For elliptic curve operations, `libsecp256k1`_ is a required dependency::

    sudo apt-get install libsecp256k1-0

Alternatively, when running from a cloned repository, a script is provided to build
libsecp256k1 yourself::

    ./contrib/make_libsecp256k1.sh

Due to the need for fast symmetric ciphers, either one of `pycryptodomex`_
or `cryptography`_ is required. Install from your package manager
(or from pip)::

    sudo apt-get install python3-cryptography


If you would like hardware wallet support, see `this`_.

.. _libsecp256k1: https://github.com/bitcoin-core/secp256k1
.. _pycryptodomex: https://github.com/Legrandin/pycryptodome
.. _cryptography: https://github.com/pyca/cryptography
.. _this: https://github.com/spesmilo/electrum-docs/blob/master/hardware-linux.rst

Running from tar.gz
-------------------

If you downloaded the official package (tar.gz), you can run
Actilectrum from its root directory without installing it on your
system; all the pure python dependencies are included in the 'packages'
directory. To run Actilectrum from its root directory, just do::

    ./run_actilectrum

You can also install Actilectrum on your system, by running this command::

    sudo apt-get install python3-setuptools python3-pip
    python3 -m pip install --user .

This will download and install the Python dependencies used by
Actilectrum instead of using the 'packages' directory.


Development version (git clone)
-------------------------------

Check out the code from GitHub::

    git clone git://github.com/Actinium-project/Actilectrum.git
    cd Actilectrum
    git submodule update --init

Run install (this should install dependencies)::

    python3 -m pip install --user .


Create translations (optional)::

    sudo apt-get install python-requests gettext
    ./contrib/pull_locale




Creating Binaries
=================

Linux (tarball)
---------------

See :code:`contrib/build-linux/README.md`.


Linux (AppImage)
----------------

See :code:`contrib/build-linux/appimage/README.md`.


Mac OS X / macOS
----------------

See :code:`contrib/osx/README.md`.


Windows
-------

See :code:`contrib/build-wine/README.md`.


Android
-------

See :code:`actilectrum/gui/kivy/Readme.md`.
