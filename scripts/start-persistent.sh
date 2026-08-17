#!/usr/bin/env bash
set -e

cd /app

HOMEDIR="/app/.exrpd"
CHAINID="$CHAIN_ID"
LOCAL_NODE_SCRIPT="/tmp/local-node-${MONIKER}.sh"

if [ ! -f "$HOMEDIR/config/genesis.json" ]; then
  echo "$CHAIN_LABEL ainda não inicializada. Criando genesis com chain-id $CHAINID..."

  cp /app/local-node.sh "$LOCAL_NODE_SCRIPT"

  sed -i "s/^CHAINID=.*/CHAINID=\"$CHAINID\"/" "$LOCAL_NODE_SCRIPT"
  sed -i "s/^MONIKER=.*/MONIKER=\"$MONIKER\"/" "$LOCAL_NODE_SCRIPT"

  exec bash "$LOCAL_NODE_SCRIPT"
fi

echo "$CHAIN_LABEL já inicializada. Subindo estado existente com chain-id $CHAINID..."

exec /app/bin/exrpd start \
  --metrics \
  --log_level info \
  --json-rpc.api eth,txpool,personal,net,debug,web3 \
  --home "$HOMEDIR" \
  --chain-id "$CHAINID"