import argparse
import json
import subprocess
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from eth_utils import keccak


ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT_DIR / "config"
ENV_FILE = ROOT_DIR / ".env"
LOG_FILE = ROOT_DIR / "tests" / "logfile.jsonl"
TESTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS_DIR))

from utils.converter import get_compressed_pubkey, get_private_key  # noqa: E402
from utils.make import (  # noqa: E402
    make_any,
    make_auth_info,
    make_fee,
    make_msg_transfer,
    make_pubkey,
    make_sign_doc,
    make_signer_info,
    make_tx_body,
    make_tx_raw,
)


TRANSFER_AMOUNT = Decimal("1")
FEE_AMOUNT = Decimal("0.02")
GAS_LIMIT = 400000
TIMEOUT_SECONDS = 1000
IBC_TRANSFER_TYPE_URL = "/ibc.applications.transfer.v1.MsgTransfer"
ETH_PUBKEY_TYPE_URL = "/ethermint.crypto.v1.ethsecp256k1.PubKey"


class TransferError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Envia uma transferencia IBC entre duas chains XRPL usando as "
            "chains e contas declaradas em config/."
        )
    )
    parser.add_argument("source_chain", help="name da chain de origem")
    parser.add_argument("source_account", help="name da conta de origem")
    parser.add_argument("destination_chain", help="name da chain de destino")
    parser.add_argument("destination_account", help="name da conta de destino")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TransferError(f"Arquivo de configuracao nao encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise TransferError(
            f"JSON invalido em {path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc


def required_string(document: dict[str, Any], field: str, context: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TransferError(f"{context}: campo obrigatorio invalido: {field}")
    return value.strip()


def load_env_value(name: str) -> str:
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise TransferError(f"Arquivo de ambiente nao encontrado: {ENV_FILE}") from exc

    for original in lines:
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() != name:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value:
            return value
        break

    raise TransferError(f"Variavel obrigatoria ausente em {ENV_FILE}: {name}")


def load_chain(name: str) -> dict[str, Any]:
    document = load_json(CONFIG_DIR / "chains.json")
    chains = document.get("chains") if isinstance(document, dict) else None
    if not isinstance(chains, list):
        raise TransferError("config/chains.json: chains deve ser uma lista")

    for chain in chains:
        if not isinstance(chain, dict):
            continue
        identifiers = (chain.get("name"), chain.get("service"), chain.get("chain_id"))
        if name in identifiers:
            required_string(chain, "name", f"chain {name}")
            required_string(chain, "chain_id", f"chain {name}")
            ports = chain.get("ports")
            if not isinstance(ports, dict):
                raise TransferError(f"chain {name}: ports deve ser um objeto")
            for port_name in ("rpc", "rest"):
                try:
                    port = int(ports.get(port_name))
                except (TypeError, ValueError) as exc:
                    raise TransferError(
                        f"chain {name}: porta invalida: {port_name}"
                    ) from exc
                if port <= 0:
                    raise TransferError(f"chain {name}: porta invalida: {port_name}")
            return chain

    raise TransferError(f"Chain nao encontrada em config/chains.json: {name}")


def load_account(name: str, chain_name: str) -> dict[str, Any]:
    document = load_json(CONFIG_DIR / "user-accounts.json")
    accounts = document.get("accounts") if isinstance(document, dict) else None
    if not isinstance(accounts, list):
        raise TransferError("config/user-accounts.json: accounts deve ser uma lista")

    matches = [
        account
        for account in accounts
        if isinstance(account, dict) and account.get("name") == name
    ]
    if len(matches) != 1:
        raise TransferError(
            f"Esperada exatamente uma conta '{name}' em config/user-accounts.json; "
            f"encontradas {len(matches)}"
        )

    account = matches[0]
    memberships = account.get("chains")
    if not isinstance(memberships, list) or chain_name not in memberships:
        raise TransferError(f"A conta {name} nao pertence a chain {chain_name}")
    required_string(account, "cosmos_address", f"conta {name}")
    return account


def load_asset() -> tuple[str, str, int]:
    profile = load_json(CONFIG_DIR / "profile.json")
    asset = profile.get("native_asset") if isinstance(profile, dict) else None
    if not isinstance(asset, dict):
        raise TransferError("config/profile.json: native_asset deve ser um objeto")

    denom = required_string(asset, "denom", "config/profile.json: native_asset")
    symbol = required_string(asset, "symbol", "config/profile.json: native_asset")
    try:
        decimals = int(asset.get("decimals"))
    except (TypeError, ValueError) as exc:
        raise TransferError(
            "config/profile.json: native_asset.decimals invalido"
        ) from exc
    if decimals < 0:
        raise TransferError(
            "config/profile.json: native_asset.decimals nao pode ser negativo"
        )
    return denom, symbol, decimals


def to_base_units(amount: Decimal, decimals: int) -> int:
    scaled = amount * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise TransferError(
            f"A quantidade possui mais de {decimals} casas decimais"
        )
    return int(scaled)


def load_yui_paths() -> dict[str, Any]:
    container_name = load_env_value("YUI_RELAYER_CONTAINER")
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                container_name,
                "yrly",
                "paths",
                "list",
                "--json",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise TransferError("Docker nao encontrado no PATH") from exc

    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()
        raise TransferError(
            f"Nao foi possivel consultar os paths do YUI: {details}"
        )
    try:
        paths = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise TransferError("O YUI retornou uma lista de paths invalida") from exc
    if not isinstance(paths, dict):
        raise TransferError("O YUI retornou uma lista de paths invalida")
    return paths


def find_source_endpoint(
    source_chain_id: str,
    destination_chain_id: str,
) -> tuple[str, dict[str, Any]]:
    matches: list[tuple[str, dict[str, Any]]] = []
    for path_name, path in load_yui_paths().items():
        if not isinstance(path_name, str) or not isinstance(path, dict):
            continue
        src = path.get("src")
        dst = path.get("dst")
        if not isinstance(src, dict) or not isinstance(dst, dict):
            continue
        if (
            src.get("chain-id") == source_chain_id
            and dst.get("chain-id") == destination_chain_id
        ):
            matches.append((path_name, src))
        elif (
            dst.get("chain-id") == source_chain_id
            and src.get("chain-id") == destination_chain_id
        ):
            matches.append((path_name, dst))

    if not matches:
        raise TransferError(
            "Nenhum path YUI conecta as chains informadas: "
            f"{source_chain_id} -> {destination_chain_id}"
        )
    if len(matches) > 1:
        names = ", ".join(name for name, _ in matches)
        raise TransferError(
            f"Mais de um path conecta as chains informadas: {names}"
        )

    path_name, endpoint = matches[0]
    for field in ("port-id", "channel-id"):
        if not isinstance(endpoint.get(field), str) or not endpoint[field]:
            raise TransferError(f"Path {path_name} ainda nao possui {field}")
    return path_name, endpoint


def get_account_info(
    chain: dict[str, Any],
    address: str,
) -> tuple[int, int]:
    rest_port = int(chain["ports"]["rest"])
    url = f"http://127.0.0.1:{rest_port}/cosmos/auth/v1beta1/accounts/{address}"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    account = response.json().get("account")
    if not isinstance(account, dict):
        raise TransferError(f"Resposta de conta invalida em {chain['name']}")
    base_account = account.get("base_account", account)
    if not isinstance(base_account, dict):
        raise TransferError(f"Base account invalida em {chain['name']}")
    try:
        return int(base_account["account_number"]), int(base_account["sequence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TransferError(
            f"Account number ou sequence invalido em {chain['name']}"
        ) from exc


def broadcast_tx(chain: dict[str, Any], tx_raw: bytes) -> dict[str, Any]:
    rpc_port = int(chain["ports"]["rpc"])
    url = f"http://127.0.0.1:{rpc_port}/broadcast_tx_sync"
    response = requests.get(
        url,
        params={"tx": "0x" + tx_raw.hex()},
        timeout=30,
    )
    response.raise_for_status()
    document = response.json()
    result = document.get("result") if isinstance(document, dict) else None
    if not isinstance(result, dict):
        raise TransferError(f"Resposta de broadcast invalida: {document}")
    return result


def transfer_cross_chain(
    source_chain: dict[str, Any],
    source_account: dict[str, Any],
    destination_chain: dict[str, Any],
    destination_account: dict[str, Any],
) -> dict[str, Any]:
    source_chain_id = required_string(source_chain, "chain_id", "source chain")
    destination_chain_id = required_string(
        destination_chain, "chain_id", "destination chain"
    )
    path_name, source_endpoint = find_source_endpoint(
        source_chain_id,
        destination_chain_id,
    )

    source_address = required_string(
        source_account, "cosmos_address", "source account"
    )
    destination_address = required_string(
        destination_account, "cosmos_address", "destination account"
    )
    private_key_text = required_string(
        source_account, "private_key", "source account"
    ).removeprefix("0x")
    private_key = get_private_key(private_key_text)
    public_key = get_compressed_pubkey(private_key)
    account_number, sequence = get_account_info(source_chain, source_address)

    denom, symbol, decimals = load_asset()
    transfer_amount = to_base_units(TRANSFER_AMOUNT, decimals)
    fee_amount = to_base_units(FEE_AMOUNT, decimals)
    timeout_timestamp = int((time.time() + TIMEOUT_SECONDS) * 1_000_000_000)

    message = make_msg_transfer(
        source_port=source_endpoint["port-id"],
        source_channel=source_endpoint["channel-id"],
        sender=source_address,
        receiver=destination_address,
        amount=str(transfer_amount),
        denom=denom,
        timeout_timestamp=timeout_timestamp,
    )
    message_any = make_any(IBC_TRANSFER_TYPE_URL, message)
    tx_body = make_tx_body(message_any)
    pubkey_any = make_any(ETH_PUBKEY_TYPE_URL, make_pubkey(public_key))
    signer_info = make_signer_info(pubkey_any, sequence)
    fee = make_fee(amount=str(fee_amount), denom=denom, gas_limit=GAS_LIMIT)
    auth_info = make_auth_info(signer_info, fee)
    sign_doc = make_sign_doc(
        body_bytes=tx_body,
        auth_info_bytes=auth_info,
        chain_id=source_chain_id,
        account_number=account_number,
    )
    signature = private_key.sign_msg_hash(keccak(sign_doc)).to_bytes()
    tx_raw = make_tx_raw(
        body_bytes=tx_body,
        auth_info_bytes=auth_info,
        signature=signature,
    )
    result = broadcast_tx(source_chain, tx_raw)
    try:
        code = int(result.get("code", -1))
    except (TypeError, ValueError) as exc:
        raise TransferError(f"Codigo de broadcast invalido: {result}") from exc

    return {
        "Path": path_name,
        "Source Chain": source_chain["name"],
        "Source Chain ID": source_chain_id,
        "Source Account": source_account["name"],
        "Destination Chain": destination_chain["name"],
        "Destination Chain ID": destination_chain_id,
        "Destination Account": destination_account["name"],
        "Source Port": source_endpoint["port-id"],
        "Source Channel": source_endpoint["channel-id"],
        "Sender": source_address,
        "Receiver": destination_address,
        "Amount": f"{TRANSFER_AMOUNT} {symbol}",
        f"Amount {denom}": str(transfer_amount),
        "Code": code,
        "TxHash": result.get("hash"),
        "Log": result.get("log"),
    }


def main() -> int:
    args = parse_args()
    try:
        source_chain = load_chain(args.source_chain)
        destination_chain = load_chain(args.destination_chain)
        source_account = load_account(args.source_account, source_chain["name"])
        destination_account = load_account(
            args.destination_account,
            destination_chain["name"],
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
