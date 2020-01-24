#!/bin/bash

set -e

APPDIR="$(dirname "$(readlink -e "$0")")"

export LD_LIBRARY_PATH="${APPDIR}/usr/lib/:${APPDIR}/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH+:$LD_LIBRARY_PATH}"
export PATH="${APPDIR}/usr/bin:${PATH}"
export LDFLAGS="-L${APPDIR}/usr/lib/x86_64-linux-gnu -L${APPDIR}/usr/lib"

<<<<<<< HEAD
exec "${APPDIR}/usr/bin/python3.6" -s "${APPDIR}/usr/bin/actilectrum" "$@"
=======
exec "${APPDIR}/usr/bin/python3.7" -s "${APPDIR}/usr/bin/electrum-ltc" "$@"
>>>>>>> 738fc9a8ea542faec20344f5fb5bed51625da5e7
