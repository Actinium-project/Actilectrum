Actilectrum - Lightweight Actinium client
==========================================

Actilectrum is a port of Electrum, the Bitcoin wallet, to Actinium.

::

  Licence: MIT Licence
  Original Author: Thomas Voegtlin
  Port Maintainer: Harris Brakmic
  Language: Python (>= 3.6)
  Homepage: https://actilectrum.org/






Getting started
===============

Actilectrum is a pure python application. If you want to use the
Qt interface, install the Qt dependencies::

    sudo apt-get install python3-pyqt5

If you downloaded the official package (tar.gz), you can run
Actilectrum from its root directory without installing it on your
system; all the python dependencies are included in the 'packages'
directory. To run Actilectrum from its root directory, just do::

    ./run_actilectrum

You can also install Actilectrum on your system, by running this command::

    sudo apt-get install python3-setuptools
    python3 -m pip install .[fast]

This will download and install the Python dependencies used by
Actilectrum instead of using the 'packages' directory.
The 'fast' extra contains some optional dependencies that we think
are often useful but they are not strictly needed.

If you cloned the git repository, you need to compile extra files
before you can run Actilectrum. Read the next section, "Development
Version".



Development version
===================

Check out the code from GitHub::

    git clone git://github.com/Actinium-project/actilectrum.git
    cd actilectrum

Run install (this should install dependencies)::

    python3 -m pip install .[fast]

Render the SVG icons to PNGs (optional)::

    for i in lock unlock confirmed status_lagging status_disconnected status_connected_proxy status_connected status_waiting preferences; do convert -background none icons/$i.svg icons/$i.png; done

Compile the icons file for Qt::

    sudo apt-get install pyqt5-dev-tools
    pyrcc5 icons.qrc -o actilectrum/gui/qt/icons_rc.py

Compile the protobuf description file::

    sudo apt-get install protobuf-compiler
    protoc --proto_path=actilectrum --python_out=actilectrum actilectrum/paymentrequest.proto

Create translations (optional)::

    sudo apt-get install python-requests gettext
    ./contrib/make_locale




Creating Binaries
=================

Linux
-----

See :code:`contrib/build-linux/README.md`.


Mac OS X / macOS
----------------

See :code:`contrib/osx/README.md`.


Windows
-------

See :code:`contrib/build-wine/docker/README.md`.


Android
-------

See :code:`actilectrum/gui/kivy/Readme.md`.
