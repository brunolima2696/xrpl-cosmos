#!/usr/bin/env bash

set -euo pipefail

CONTAINER="${1:-cosmos_chain_1}"
NETWORK="${2:-interoperability_network}"
ALIAS="${3:-$CONTAINER}"

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
	echo "Rede Docker nao encontrada: $NETWORK" >&2
	exit 1
fi

if ! docker container inspect "$CONTAINER" >/dev/null 2>&1; then
	echo "Container Docker nao encontrado: $CONTAINER" >&2
	exit 1
fi

if docker container inspect \
	--format '{{json .NetworkSettings.Networks}}' \
	"$CONTAINER" | grep -q "\"$NETWORK\""; then
	echo "$CONTAINER ja esta conectado a rede $NETWORK."
	exit 0
fi

echo "Conectando $CONTAINER a rede $NETWORK com o alias $ALIAS..."
docker network connect --alias "$ALIAS" "$NETWORK" "$CONTAINER"
echo "Conexao concluida."
