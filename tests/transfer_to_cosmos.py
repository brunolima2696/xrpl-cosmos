import argparse
import json
import sys
from pathlib import Path
from typing import Any

import requests

from utils.environment import load_env_path

from transfer_to_xrpl import (
    LOG_FILE,
    TransferError,
    load_account as load_xrpl_account,
    load_chain as load_xrpl_chain,
    load_json,
    required_string,
    transfer_cross_chain,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"


def yui_manifest_path() -> Path:
    runtime_dir = load_env_path(
        ENV_FILE,
        "YUI_RELAYER_RUNTIME",
        ROOT_DIR,
    )
    return runtime_dir / "manifest.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Envia uma transferencia IBC de uma chain XRPL para uma chain "
            "Cosmos usando os descritores dos modulos registrados no YUI."
        )
    )
    parser.add_argument("source_chain", help="name da chain XRPL de origem")
    parser.add_argument("source_account", help="name da conta XRPL de origem")
    parser.add_argument("destination_chain", help="name da chain Cosmos de destino")
    parser.add_argument("destination_account", help="name da conta Cosmos de destino")
    return parser.parse_args()


def manifest_chain(name: str) -> tuple[str, dict[str, Any]]:
    manifest = yui_manifest_path()
    document = load_json(manifest)
    chains = document.get("chains") if isinstance(document, dict) else None
    if not isinstance(chains, dict):
        raise TransferError(f"{manifest}: chains deve ser um objeto")

    matches: list[tuple[str, dict[str, Any]]] = []
    for chain_name, entry in chains.items():
        if not isinstance(chain_name, str) or not isinstance(entry, dict):
            continue
        identifiers = (chain_name, entry.get("chain_id"), entry.get("service"))
        if name in identifiers:
            matches.append((chain_name, entry))

    if len(matches) != 1:
        raise TransferError(
            f"Esperada exatamente uma chain '{name}' em {manifest}; "
            f"encontradas {len(matches)}"
        )
    return matches[0]


def load_chain_from_file(path: Path, name: str) -> dict[str, Any]:
    document = load_json(path)
    chains = document.get("chains") if isinstance(document, dict) else None
    if not isinstance(chains, list):
        raise TransferError(f"{path}: chains deve ser uma lista")

    matches = []
    for chain in chains:
        if not isinstance(chain, dict):
            continue
        identifiers = (chain.get("name"), chain.get("service"), chain.get("chain_id"))
        if name in identifiers:
            matches.append(chain)

    if len(matches) != 1:
        raise TransferError(
            f"Esperada exatamente uma chain '{name}' em {path}; "
            f"encontradas {len(matches)}"
        )

    chain = matches[0]
    required_string(chain, "name", f"chain {name}")
    required_string(chain, "chain_id", f"chain {name}")
    return chain


def load_account_from_file(
    path: Path,
    name: str,
    chain_name: str,
) -> dict[str, Any]:
    document = load_json(path)
    accounts = document.get("accounts") if isinstance(document, dict) else None
    if not isinstance(accounts, list):
        raise TransferError(f"{path}: accounts deve ser uma lista")

    matches = [
        account
        for account in accounts
        if isinstance(account, dict) and account.get("name") == name
    ]
    if len(matches) != 1:
        raise TransferError(
            f"Esperada exatamente uma conta '{name}' em {path}; "
            f"encontradas {len(matches)}"
        )

    account = matches[0]
    memberships = account.get("chains")
    if not isinstance(memberships, list) or chain_name not in memberships:
        raise TransferError(f"A conta {name} nao pertence a chain {chain_name}")
    required_string(account, "cosmos_address", f"conta {name}")
    return account


def load_cosmos_destination(
    chain_name: str,
    account_name: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_name, entry = manifest_chain(chain_name)
    chains_source = Path(
        required_string(entry, "chains_source", f"manifest chain {manifest_name}")
    )
    accounts_source = chains_source.with_name("user-accounts.json")
    chain = load_chain_from_file(chains_source, chain_name)
    account = load_account_from_file(accounts_source, account_name, manifest_name)
    return chain, account


def main() -> int:
    args = parse_args()
    try:
        source_chain = load_xrpl_chain(args.source_chain)
        source_account = load_xrpl_account(
            args.source_account,
            source_chain["name"],
        )
        destination_chain, destination_account = load_cosmos_destination(
            args.destination_chain,
            args.destination_account,
        )
        output = transfer_cross_chain(
            source_chain,
            source_account,
            destination_chain,
            destination_account,
        )
    except (TransferError, requests.RequestException, ValueError) as exc:
        print(f"Falha: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(output, indent=2, ensure_ascii=False))
    if output["Code"] == 0:
        with LOG_FILE.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(output, ensure_ascii=False) + "\n")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
