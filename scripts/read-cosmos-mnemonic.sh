#!/usr/bin/env bash

set -euo pipefail

CONTAINER="${1:-cosmos_chain_1}"
SEED_FILE="${2:-/opt/cosmos/testdata/cosmos_chain_1/relayer_seed.json}"

if ! docker container inspect "$CONTAINER" >/dev/null 2>&1; then
	echo "Container Docker não encontrado: $CONTAINER" >&2
	exit 1
fi

if [ "$(docker container inspect --format '{{.State.Running}}' "$CONTAINER")" != "true" ]; then
	echo "Container Docker não está em execução: $CONTAINER" >&2
	exit 1
fi

MSYS_NO_PATHCONV=1 docker exec "$CONTAINER" \
	jq -er '.mnemonic | select(type == "string" and length > 0)' "$SEED_FILE"
