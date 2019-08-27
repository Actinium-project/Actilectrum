#!/usr/bin/env bash
export HOME=~
set -eu

# alice -> bob -> carol

alice="./run_electrum --regtest --lightning -D /tmp/alice"
bob="./run_electrum --regtest --lightning -D /tmp/bob"
carol="./run_electrum --regtest --lightning -D /tmp/carol"

bitcoin_cli="litecoin-cli -rpcuser=doggman -rpcpassword=donkey -rpcport=18554 -regtest"

function new_blocks()
{
    $bitcoin_cli generatetoaddress $1 $($bitcoin_cli getnewaddress) > /dev/null
}

function wait_until_funded()
{
    while alice_balance=$($alice getbalance | jq '.confirmed' | tr -d '"') && [ $alice_balance != "1" ]; do
        echo "waiting for alice balance"
        sleep 1
    done
}

function wait_until_channel_open()
{
    while channel_state=$($alice list_channels | jq '.[] | .state' | tr -d '"') && [ $channel_state != "OPEN" ]; do
        echo "waiting for channel open"
        sleep 1
    done
}

if [[ $# -eq 0 ]]; then
    echo "syntax: init|start|open|status|pay|close|stop"
    exit 1
fi

if [[ $1 == "init" ]]; then
    echo "initializing alice, bob and carol"
    rm -rf /tmp/alice/ /tmp/bob/ /tmp/carol/
    $alice create > /dev/null
    $bob create > /dev/null
    $carol create > /dev/null
    $alice setconfig log_to_file True
    $bob   setconfig log_to_file True
    $carol setconfig log_to_file True
    $alice setconfig server 127.0.0.1:51001:t
    $bob   setconfig server 127.0.0.1:51001:t
    $carol setconfig server 127.0.0.1:51001:t
    $bob setconfig lightning_listen localhost:9735
    $bob setconfig lightning_forward_payments true
    echo "funding alice and carol"
    $bitcoin_cli sendtoaddress $($alice getunusedaddress) 1
    $bitcoin_cli sendtoaddress $($carol getunusedaddress) 1
    new_blocks 1
fi

# start daemons. Bob is started first because he is listening
if [[ $1 == "start" ]]; then
    $bob daemon start
    $alice daemon start
    $carol daemon start
    sleep 1 # time to accept commands
    $bob load_wallet
    $alice load_wallet
    $carol load_wallet
    sleep 10 # give time to synchronize
fi

if [[ $1 == "stop" ]]; then
    $alice stop || true
    $bob stop || true
    $carol stop || true
fi

if [[ $1 == "open" ]]; then
    bob_node=$($bob nodeid)
    channel_id1=$($alice open_channel $bob_node 0.001 --channel_push 0.001)
    channel_id2=$($carol open_channel $bob_node 0.001 --channel_push 0.001)
    echo "mining 3 blocks"
    new_blocks 3
    sleep 10 # time for channelDB
fi

if [[ $1 == "alice_pays_carol" ]]; then
    request=$($carol addinvoice 0.0001 "blah")
    $alice lnpay $request
    carol_balance=$($carol list_channels | jq -r '.[0].local_balance')
    echo "carol balance: $carol_balance"
    if [[ $carol_balance != 110000 ]]; then
        exit 1
    fi
fi

if [[ $1 == "close" ]]; then
   chan1=$($alice list_channels | jq -r ".[0].channel_point")
   chan2=$($carol list_channels | jq -r ".[0].channel_point")
   $alice close_channel $chan1
   $carol close_channel $chan2
   echo "mining 1 block"
   new_blocks 1
fi

# alice sends two payments, then broadcast ctx after first payment.
# thus, bob needs to redeem both to_local and to_remote

if [[ $1 == "breach" ]]; then
    bob_node=$($bob nodeid)
    channel=$($alice open_channel $bob_node 0.15)
    new_blocks 3
    wait_until_channel_open
    request=$($bob addinvoice 0.01 "blah")
    echo "alice pays"
    $alice lnpay $request
    sleep 2
    ctx=$($alice get_channel_ctx $channel | jq '.hex' | tr -d '"')
    request=$($bob addinvoice 0.01 "blah2")
    echo "alice pays"
    $alice lnpay $request
    sleep 2
    echo "alice broadcasts old ctx"
    $bitcoin_cli sendrawtransaction $ctx
    sleep 10
    new_blocks 2
    sleep 10
    balance=$($bob getbalance | jq '.confirmed | tonumber')
    echo "balance of bob after breach: $balance"
    if (( $(echo "$balance < 0.14" | bc -l) )); then
        exit 1
    fi
fi

if [[ $1 == "redeem_htlcs" ]]; then
    $bob stop
    ELECTRUM_DEBUG_LIGHTNING_SETTLE_DELAY=10 $bob daemon start
    sleep 1
    $bob load_wallet
    sleep 1
    # alice opens channel
    bob_node=$($bob nodeid)
    $alice open_channel $bob_node 0.15
    new_blocks 6
    sleep 10
    # alice pays bob
    invoice=$($bob addinvoice 0.05 "test")
    $alice lnpay $invoice --timeout=1 || true
    sleep 1
    settled=$($alice list_channels | jq '.[] | .local_htlcs | .settles | length')
    if [[ "$settled" != "0" ]]; then
        echo 'SETTLE_DELAY did not work'
        exit 1
    fi
    # bob goes away
    $bob stop
    echo "alice balance before closing channel:" $($alice getbalance)
    balance_before=$($alice getbalance | jq '[.confirmed, .unconfirmed, .lightning] | to_entries | map(select(.value != null).value) | map(tonumber) | add ')
    # alice force closes the channel
    chan_id=$($alice list_channels | jq -r ".[0].channel_point")
    $alice close_channel $chan_id --force
    new_blocks 1
    sleep 3
    echo "alice balance after closing channel:" $($alice getbalance)
    new_blocks 150
    sleep 10
    new_blocks 1
    sleep 3
    echo "alice balance after CLTV" $($alice getbalance)
    new_blocks 150
    sleep 10
    new_blocks 1
    sleep 3
    echo "alice balance after CSV" $($alice getbalance)
    balance_after=$($alice getbalance |  jq '[.confirmed, .unconfirmed] | to_entries | map(select(.value != null).value) | map(tonumber) | add ')
    if (( $(echo "$balance_before - $balance_after > 0.02" | bc -l) )); then
        echo "htlc not redeemed."
        exit 1
    fi
fi


if [[ $1 == "breach_with_unspent_htlc" ]]; then
    $bob stop
    ELECTRUM_DEBUG_LIGHTNING_SETTLE_DELAY=3 $bob daemon start
    sleep 1
    $bob load_wallet
    wait_until_funded
    echo "alice opens channel"
    bob_node=$($bob nodeid)
    channel=$($alice open_channel $bob_node 0.15)
    new_blocks 3
    wait_until_channel_open
    echo "alice pays bob"
    invoice=$($bob addinvoice 0.05 "test")
    $alice lnpay $invoice --timeout=1 || true
    settled=$($alice list_channels | jq '.[] | .local_htlcs | .settles | length')
    if [[ "$settled" != "0" ]]; then
        echo "SETTLE_DELAY did not work, $settled != 0"
        exit 1
    fi
    ctx=$($alice get_channel_ctx $channel | jq '.hex' | tr -d '"')
    sleep 5
    settled=$($alice list_channels | jq '.[] | .local_htlcs | .settles | length')
    if [[ "$settled" != "1" ]]; then
        echo "SETTLE_DELAY did not work, $settled != 1"
        exit 1
    fi
    echo $($bob getbalance)
    echo "alice breaches with old ctx"
    echo $ctx
    height1=$($bob getinfo | jq '.blockchain_height')
    $bitcoin_cli sendrawtransaction $ctx
    new_blocks 1
    # wait until breach is confirmed
    while height2=$($bob getinfo | jq '.blockchain_height') && [ $(($height2 - $height1)) -ne 1 ]; do
        echo "waiting for block"
        sleep 1
    done
    new_blocks 1
    # wait until next block is confirmed, so that htlc tx and redeem tx are confirmed too
    while height3=$($bob getinfo | jq '.blockchain_height') && [ $(($height3 - $height2)) -ne 1 ]; do
        echo "waiting for block"
        sleep 1
    done
    # wait until wallet is synchronized
    while b=$($bob list_wallets | jq '.[0]|.synchronized') && [ "$b" != "true" ]; do
        echo "waiting for wallet sync: $b"
        sleep 1
    done
    echo $($bob getbalance)
    balance_after=$($bob getbalance | jq '[.confirmed, .unconfirmed] | to_entries | map(select(.value != null).value) | map(tonumber) | add ')
    if (( $(echo "$balance_after < 0.14" | bc -l) )); then
        echo "htlc not redeemed."
        exit 1
    fi
fi


if [[ $1 == "breach_with_spent_htlc" ]]; then
    $bob stop
    ELECTRUM_DEBUG_LIGHTNING_SETTLE_DELAY=3 $bob daemon start
    sleep 1
    $bob load_wallet
    wait_until_funded
    echo "alice opens channel"
    bob_node=$($bob nodeid)
    channel=$($alice open_channel $bob_node 0.15)
    new_blocks 3
    wait_until_channel_open
    echo "alice pays bob"
    invoice=$($bob addinvoice 0.05 "test")
    $alice lnpay $invoice --timeout=1 || true
    ctx=$($alice get_channel_ctx $channel | jq '.hex' | tr -d '"')
    settled=$($alice list_channels | jq '.[] | .local_htlcs | .settles | length')
    if [[ "$settled" != "0" ]]; then
        echo "SETTLE_DELAY did not work, $settled != 0"
        exit 1
    fi
    cp /tmp/alice/regtest/wallets/default_wallet /tmp/alice/regtest/wallets/toxic_wallet
    sleep 5
    settled=$($alice list_channels | jq '.[] | .local_htlcs | .settles | length')
    if [[ "$settled" != "1" ]]; then
        echo "SETTLE_DELAY did not work, $settled != 1"
        exit 1
    fi
    echo $($bob getbalance)
    echo "bob goes offline"
    $bob stop
    ctx_id=$($bitcoin_cli sendrawtransaction $ctx)
    echo "alice breaches with old ctx:" $ctx_id
    new_blocks 1
    if [[ $($bitcoin_cli gettxout $ctx_id 0 | jq '.confirmations') != "1" ]]; then
        echo "breach tx not confirmed"
        exit 1
    fi
    echo "wait for cltv_expiry blocks"
    # note: this will let alice redeem both to_local and the htlc.
    # (to_local needs to_self_delay blocks; htlc needs whatever we put in invoice)
    new_blocks 150
    echo "alice spends to_local and htlc outputs"
    $alice stop
    cp /tmp/alice/regtest/wallets/toxic_wallet /tmp/alice/regtest/wallets/default_wallet
    $alice daemon start
    sleep 1
    $alice load_wallet
    # wait until alice has spent both ctx outputs
    while [[ $($bitcoin_cli gettxout $ctx_id 0) ]]; do
        echo "waiting until alice spends ctx outputs"
        sleep 1
    done
    while [[ $($bitcoin_cli gettxout $ctx_id 1) ]]; do
        echo "waiting until alice spends ctx outputs"
        sleep 1
    done
    new_blocks 1
    echo "bob comes back"
    $bob daemon start
    sleep 1
    $bob load_wallet
    while [[ $($bitcoin_cli getmempoolinfo | jq '.size') != "1" ]]; do
        echo "waiting for bob's transaction"
        sleep 1
    done
    echo "mempool has 1 tx"
    new_blocks 1
    sleep 5
    balance=$($bob getbalance | jq '.confirmed')
    if (( $(echo "$balance < 0.049" | bc -l) )); then
        echo "htlc not redeemed."
        exit 1
    fi
    echo "bob balance $balance"
fi

if [[ $1 == "watchtower" ]]; then
    # carol is a watchtower of alice
    $alice stop
    $carol stop
    $alice setconfig watchtower_url http://127.0.0.1:12345
    $carol setconfig watchtower_host 127.0.0.1
    $carol setconfig watchtower_port 12345
    $carol daemon start
    $alice daemon start
    sleep 1
    $alice load_wallet
    echo "waiting until alice funded"
    wait_until_funded
    echo "alice opens channel"
    bob_node=$($bob nodeid)
    channel=$($alice open_channel $bob_node 0.5)
    new_blocks 3
    wait_until_channel_open
    echo "alice pays bob"
    invoice1=$($bob addinvoice 0.05 "invoice1")
    $alice lnpay $invoice1
    invoice2=$($bob addinvoice 0.05 "invoice2")
    $alice lnpay $invoice2
    invoice3=$($bob addinvoice 0.05 "invoice3")
    $alice lnpay $invoice3

fi
