#!/usr/bin/env bash
export HOME=~
set -eux pipefail
mkdir -p ~/.actinium
cat > ~/.actinium/actinium.conf <<EOF
regtest=1
txindex=1
printtoconsole=1
rpcuser=doggman
rpcpassword=donkey
rpcallowip=127.0.0.1
zmqpubrawblock=tcp://127.0.0.1:28332
zmqpubrawtx=tcp://127.0.0.1:28333
[regtest]
rpcbind=0.0.0.0
rpcport=18554
EOF
rm -rf ~/.actinium/regtest
screen -S Actiniumd -X quit || true
screen -S Actiniumd -m -d Actiniumd -regtest
sleep 6
addr=$(Actinium-cli getnewaddress)
actinium-cli generatetoaddress 150 $addr > /dev/null
