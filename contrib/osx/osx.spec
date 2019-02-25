# -*- mode: python -*-

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

import sys, os

PACKAGE='Actilectrum'
PYPKG='actilectrum'
MAIN_SCRIPT='run_actilectrum'
ICONS_FILE=PYPKG + '/gui/icons/actilectrum.icns'
APP_SIGN = os.environ.get('APP_SIGN', '')

def fail(*msg):
    RED='\033[0;31m'
    NC='\033[0m' # No Color
    print("\r🗯 {}ERROR:{}".format(RED, NC), *msg)
    sys.exit(1)

def codesign(identity, binary):
    d = os.path.dirname(binary)
    saved_dir=None
    if d:
        # switch to directory of the binary so codesign verbose messages don't include long path
        saved_dir = os.path.abspath(os.path.curdir)
        os.chdir(d)
        binary = os.path.basename(binary)
    os.system("codesign -v -f -s '{}' '{}'".format(identity, binary))==0 or fail("Could not code sign " + binary)
    if saved_dir:
        os.chdir(saved_dir)

def monkey_patch_pyinstaller_for_codesigning(identity):
    # Monkey-patch PyInstaller so that we app-sign all binaries *after* they are modified by PyInstaller
    # If we app-sign before that point, the signature will be invalid because PyInstaller modifies
    # @loader_path in the Mach-O loader table.
    try:
        import PyInstaller.depend.dylib
        _saved_func = PyInstaller.depend.dylib.mac_set_relative_dylib_deps
    except (ImportError, NameError, AttributeError):
        # Hmm. Likely wrong PyInstaller version.
        fail("Could not monkey-patch PyInstaller for code signing. Please ensure that you are using PyInstaller 3.4.")
    _signed = set()
    def my_func(fn, distname):
        _saved_func(fn, distname)
        if  (fn, distname) not in _signed:
            codesign(identity, fn)
            _signed.add((fn,distname)) # remember we signed it so we don't sign again
    PyInstaller.depend.dylib.mac_set_relative_dylib_deps = my_func


for i, x in enumerate(sys.argv):
    if x == '--name':
        VERSION = sys.argv[i+1]
        break
else:
    raise Exception('no version')

actilectrum = os.path.abspath(".") + "/"
block_cipher = None

# see https://github.com/pyinstaller/pyinstaller/issues/2005
hiddenimports = []
hiddenimports += collect_submodules('trezorlib')
hiddenimports += collect_submodules('safetlib')
hiddenimports += collect_submodules('btchip')
hiddenimports += collect_submodules('keepkeylib')
hiddenimports += collect_submodules('websocket')
hiddenimports += collect_submodules('ckcc')

# safetlib imports PyQt5.Qt.  We use a local updated copy of pinmatrix.py until they
# release a new version that includes https://github.com/archos-safe-t/python-safet/commit/b1eab3dba4c04fdfc1fcf17b66662c28c5f2380e
hiddenimports.remove('safetlib.qt.pinmatrix')


datas = [
    (actilectrum + PYPKG + '/*.json', PYPKG),
    (actilectrum + PYPKG + '/wordlist/english.txt', PYPKG + '/wordlist'),
    (actilectrum + PYPKG + '/locale', PYPKG + '/locale'),
    (actilectrum + PYPKG + '/plugins', PYPKG + '/plugins'),
    (actilectrum + PYPKG + '/gui/icons', PYPKG + '/gui/icons'),
]
datas += collect_data_files('trezorlib')
datas += collect_data_files('safetlib')
datas += collect_data_files('btchip')
datas += collect_data_files('keepkeylib')
datas += collect_data_files('ckcc')

# Add the QR Scanner helper app
datas += [(actilectrum + "contrib/osx/CalinsQRReader/build/Release/CalinsQRReader.app", "./contrib/osx/CalinsQRReader/build/Release/CalinsQRReader.app")]

# Add libusb so Trezor and Safe-T mini will work
binaries = [(actilectrum + "contrib/osx/libusb-1.0.dylib", ".")]
binaries += [(actilectrum + "contrib/osx/libsecp256k1.0.dylib", ".")]

# Workaround for "Retro Look":
binaries += [b for b in collect_dynamic_libs('PyQt5') if 'macstyle' in b[0]]

# We don't put these files in to actually include them in the script but to make the Analysis method scan them for imports
a = Analysis([actilectrum+ MAIN_SCRIPT,
              actilectrum+'actilectrum/gui/qt/main_window.py',
              actilectrum+'actilectrum/gui/text.py',
              actilectrum+'actilectrum/util.py',
              actilectrum+'actilectrum/wallet.py',
              actilectrum+'actilectrum/simple_config.py',
              actilectrum+'actilectrum/bitcoin.py',
              actilectrum+'actilectrum/blockchain.py',
              actilectrum+'actilectrum/dnssec.py',
              actilectrum+'actilectrum/commands.py',
              actilectrum+'actilectrum/plugins/cosigner_pool/qt.py',
              actilectrum+'actilectrum/plugins/email_requests/qt.py',
              actilectrum+'actilectrum/plugins/trezor/qt.py',
              actilectrum+'actilectrum/plugins/safe_t/client.py',
              actilectrum+'actilectrum/plugins/safe_t/qt.py',
              actilectrum+'actilectrum/plugins/keepkey/qt.py',
              actilectrum+'actilectrum/plugins/ledger/qt.py',
              actilectrum+'actilectrum/plugins/coldcard/qt.py',
              ],
             binaries=binaries,
             datas=datas,
             hiddenimports=hiddenimports,
             hookspath=[])

# http://stackoverflow.com/questions/19055089/pyinstaller-onefile-warning-pyconfig-h-when-importing-scipy-or-scipy-signal
for d in a.datas:
    if 'pyconfig' in d[0]:
        a.datas.remove(d)
        break

# Strip out parts of Qt that we never use. Reduces binary size by tens of MBs. see #4815
qt_bins2remove=('qtweb', 'qt3d', 'qtgame', 'qtdesigner', 'qtquick', 'qtlocation', 'qttest', 'qtxml')
print("Removing Qt binaries:", *qt_bins2remove)
for x in a.binaries.copy():
    for r in qt_bins2remove:
        if x[0].lower().startswith(r):
            a.binaries.remove(x)
            print('----> Removed x =', x)

# If code signing, monkey-patch in a code signing step to pyinstaller. See: https://github.com/spesmilo/actilectrum/issues/4994
if APP_SIGN:
    monkey_patch_pyinstaller_for_codesigning(APP_SIGN)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.datas,
          name=PACKAGE,
          debug=False,
          strip=False,
          upx=True,
          icon=actilectrum+ICONS_FILE,
          console=False)

app = BUNDLE(exe,
             version = VERSION,
             name=PACKAGE + '.app',
             icon=actilectrum+ICONS_FILE,
             bundle_identifier=None,
             info_plist={
                'NSHighResolutionCapable': 'True',
                'NSSupportsAutomaticGraphicsSwitching': 'True'
             }
)
