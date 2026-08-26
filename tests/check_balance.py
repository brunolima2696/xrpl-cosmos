import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests
from web3 import Web3
from web3.exceptions import Web3Exception

from utils.environment import load_env_path


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT_DIR / ".env"
LOG_BLOCK_RANGE = 1000


class BalanceError(RuntimeError):
    pass


RECV_PACKET_ABI = {
    "anonymous": False,
    "inputs": [
        {
            "components": [
                {"internalType": "uint64", "name": "sequence", "type": "uint64"},
                {"internalType": "string", "name": "sourcePort", "type": "string"},
                {
                    "internalType": "string",
                    "name": "sourceChannel",
                    "type": "string",
                },
                {
                    "internalType": "string",
                    "name": "destinationPort",
                    "type": "string",
                },
                {
                    "internalType": "string",
                    "name": "destinationChannel",
                    "type": "string",
                },
                {"internalType": "bytes", "name": "data", "type": "bytes"},
                {
                    "components": [
                        {
                            "internalType": "uint64",
                            "name": "revision_number",
                            "type": "uint64",
                        },
                        {
                            "internalType": "uint64",
                            "name": "revision_height",
                            "type": "uint64",
                        },
                    ],
                    "internalType": "struct Height.Data",
                    "name": "timeoutHeight",
                    "type": "tuple",
                },
                {
                    "internalType": "uint64",
                    "name": "timeoutTimestamp",
                    "type": "uint64",
                },
            ],
            "indexed": False,
            "internalType": "struct Packet",
            "name": "packet",
            "type": "tuple",
        }
    ],
    "name": "RecvPacket",
    "type": "event",
}

ICS20_BALANCE_ABI = {
    "inputs": [
        {"internalType": "address", "name": "account", "type": "address"},
        {"internalType": "string", "name": "denom", "type": "string"},
    ],
    "name": "balanceOf",
    "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
    "stateMutability": "view",
    "type": "function",
}

ERC20_ABI = [
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lista os saldos de uma conta declarada em uma chain registrada no YUI."
    )
    parser.add_argument("chain", help="name, chain_id ou service da chain")
    parser.add_argument("account", help="name da conta em user-accounts.json")
    return parser.parse_args()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BalanceError(f"Arquivo nao encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BalanceError(
            f"JSON invalido em {path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc


def required_string(document: dict[str, Any], field: str, context: str) -> str:
    value = document.get(field)
    if not isinstance(value, str) or not value.strip():
        raise BalanceError(f"{context}: campo obrigatorio invalido: {field}")
    return value.strip()


def yui_manifest_path() -> Path:
    runtime_dir = load_env_path(
        ENV_FILE,
        "YUI_RELAYER_RUNTIME",
        ROOT_DIR,
    )
    return runtime_dir / "manifest.json"


def resolve_manifest_chain(name: str) -> tuple[str, dict[str, Any]]:
    manifest = yui_manifest_path()
    document = load_json(manifest)
    chains = document.get("chains") if isinstance(document, dict) else None
    if not isinstance(chains, dict):
        raise BalanceError(f"{manifest}: chains deve ser um objeto")

    matches = []
    for logical_name, entry in chains.items():
        if not isinstance(logical_name, str) or not isinstance(entry, dict):
            continue
        if name in (logical_name, entry.get("chain_id"), entry.get("service")):
            matches.append((logical_name, entry))

    if len(matches) != 1:
        raise BalanceError(
            f"Esperada exatamente uma chain '{name}' no manifesto; "
            f"encontradas {len(matches)}"
        )
    return matches[0]


def select_record(
    path: Path,
    collection: str,
    name: str,
    identifiers: tuple[str, ...],
) -> dict[str, Any]:
    document = load_json(path)
    records = document.get(collection) if isinstance(document, dict) else None
    if not isinstance(records, list):
        raise BalanceError(f"{path}: {collection} deve ser uma lista")

    matches = [
        record
        for record in records
        if isinstance(record, dict)
        and name in tuple(record.get(field) for field in identifiers)
    ]
    if len(matches) != 1:
        raise BalanceError(
            f"Esperado exatamente um registro '{name}' em {path}; "
            f"encontrados {len(matches)}"
        )
    return matches[0]


def load_context(
    chain_name: str,
    account_name: str,
) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], Path]:
    logical_name, manifest_entry = resolve_manifest_chain(chain_name)
    chains_path = Path(
        required_string(manifest_entry, "chains_source", f"chain {logical_name}")
    )
    profile_path = Path(
        required_string(manifest_entry, "profile_source", f"chain {logical_name}")
    )
    accounts_path = chains_path.with_name("user-accounts.json")

    chain = select_record(
        chains_path,
        "chains",
        chain_name,
        ("name", "chain_id", "service"),
    )
    account = select_record(accounts_path, "accounts", account_name, ("name",))
    memberships = account.get("chains")
    if not isinstance(memberships, list) or logical_name not in memberships:
        raise BalanceError(
            f"A conta {account_name} nao pertence a chain {logical_name}"
        )

    profile = load_json(profile_path)
    if not isinstance(profile, dict):
        raise BalanceError(f"{profile_path}: profile deve ser um objeto")
    return logical_name, chain, account, profile, chains_path


def integer_port(chain: dict[str, Any], name: str) -> int:
    ports = chain.get("ports")
    if not isinstance(ports, dict):
        raise BalanceError(f"chain {chain.get('name')}: ports deve ser um objeto")
    try:
        port = int(ports.get(name))
    except (TypeError, ValueError) as exc:
        raise BalanceError(f"chain {chain.get('name')}: porta invalida: {name}") from exc
    if port <= 0:
        raise BalanceError(f"chain {chain.get('name')}: porta invalida: {name}")
    return port


def native_asset(profile: dict[str, Any]) -> dict[str, Any]:
    asset = profile.get("native_asset")
    if not isinstance(asset, dict):
        raise BalanceError("profile.native_asset deve ser um objeto")
    required_string(asset, "denom", "profile.native_asset")
    required_string(asset, "symbol", "profile.native_asset")
    try:
        decimals = int(asset.get("decimals"))
    except (TypeError, ValueError) as exc:
        raise BalanceError("profile.native_asset.decimals invalido") from exc
    if decimals < 0:
        raise BalanceError("profile.native_asset.decimals invalido")
    return {**asset, "decimals": decimals}


def display_amount(amount: int, decimals: int) -> str:
    value = Decimal(amount) / (Decimal(10) ** decimals)
    return format(value, "f")


def query_denom_trace(rest_url: str, denom: str) -> dict[str, str] | None:
    if not denom.startswith("ibc/"):
        return None
    try:
        response = requests.get(
            f"{rest_url}/ibc/apps/transfer/v1/denom_traces/{denom[4:]}",
            timeout=10,
        )
        response.raise_for_status()
        trace = response.json().get("denom_trace")
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(trace, dict):
        return None
    path = trace.get("path")
    base_denom = trace.get("base_denom")
    if not isinstance(path, str) or not isinstance(base_denom, str):
        return None
    return {"path": path, "base_denom": base_denom}


def tendermint_balances(
    chain: dict[str, Any],
    account: dict[str, Any],
    profile: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    address = required_string(account, "cosmos_address", f"conta {account.get('name')}")
    rest_url = f"http://127.0.0.1:{integer_port(chain, 'rest')}"
    records: list[Any] = []
    next_key = ""
    while True:
        params = {"pagination.limit": "1000"}
        if next_key:
            params["pagination.key"] = next_key
        response = requests.get(
            f"{rest_url}/cosmos/bank/v1beta1/balances/{address}",
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        document = response.json()
        page = document.get("balances") if isinstance(document, dict) else None
        if not isinstance(page, list):
            raise BalanceError("Resposta bank balances invalida")
        records.extend(page)
        pagination = document.get("pagination")
        candidate = pagination.get("next_key") if isinstance(pagination, dict) else None
        if not isinstance(candidate, str) or not candidate:
            break
        if candidate == next_key:
            raise BalanceError("Paginacao bank balances nao avancou")
        next_key = candidate

    asset = native_asset(profile)
    balances = []
    for record in records:
        if not isinstance(record, dict):
            continue
        denom = required_string(record, "denom", "bank balance")
        amount_text = required_string(record, "amount", "bank balance")
        try:
            amount = int(amount_text)
        except ValueError as exc:
            raise BalanceError(f"Saldo invalido para {denom}: {amount_text}") from exc

        item: dict[str, Any] = {
            "type": (
                "native"
                if denom == asset["denom"]
                else "ibc"
                if denom.startswith("ibc/")
                else "token"
            ),
            "denom": denom,
            "amount": str(amount),
        }
        if denom == asset["denom"]:
            item["symbol"] = asset["symbol"]
            item["decimals"] = asset["decimals"]
            item["display_amount"] = display_amount(amount, asset["decimals"])
        trace = query_denom_trace(rest_url, denom)
        if trace is not None:
            item["denom_trace"] = trace
        balances.append(item)
    return address, balances


def resolve_descriptor_path(reference: str, chains_path: Path) -> Path:
    path = Path(reference)
    if path.is_absolute() and path.is_file():
        return path
    for parent in (chains_path.parent, *chains_path.parents):
        candidate = parent / path
        if candidate.is_file():
            return candidate
    raise BalanceError(f"Arquivo referenciado nao encontrado: {reference}")


def packet_denom(packet: Any) -> str | None:
    try:
        data = json.loads(bytes(packet["data"]).decode("utf-8"))
        denom = data.get("denom")
        if not isinstance(denom, str) or not denom:
            return None
        source_prefix = f"{packet['sourcePort']}/{packet['sourceChannel']}/"
        if denom.startswith(source_prefix):
            return denom[len(source_prefix) :]
        return f"{packet['destinationPort']}/{packet['destinationChannel']}/{denom}"
    except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def known_ics20_denoms(w3: Web3, handler: str) -> set[str]:
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(handler),
        abi=[RECV_PACKET_ABI],
    )
    denoms: set[str] = set()
    latest_block = int(w3.eth.block_number)
    for first_block in range(0, latest_block + 1, LOG_BLOCK_RANGE):
        last_block = min(first_block + LOG_BLOCK_RANGE - 1, latest_block)
        events = contract.events.RecvPacket().get_logs(
            from_block=first_block,
            to_block=last_block,
        )
        for event in events:
            denom = packet_denom(event["args"]["packet"])
            if denom:
                denoms.add(denom)
    return denoms


def ethereum_balances(
    chain: dict[str, Any],
    account: dict[str, Any],
    profile: dict[str, Any],
    chains_path: Path,
) -> tuple[str, list[dict[str, Any]]]:
    address = Web3.to_checksum_address(
        required_string(account, "evm_address", f"conta {account.get('name')}")
    )
    rpc_url = f"http://127.0.0.1:{integer_port(chain, 'rpc')}"
    w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
    rpc_chain_id = int(w3.eth.chain_id)
    try:
        expected_chain_id = int(chain.get("eth_chain_id"))
    except (TypeError, ValueError) as exc:
        raise BalanceError(
            f"chain {chain.get('name')}: eth_chain_id invalido"
        ) from exc
    if rpc_chain_id != expected_chain_id:
        raise BalanceError(
            f"RPC {rpc_url} respondeu eth_chain_id={rpc_chain_id}; "
            f"esperado={expected_chain_id}"
        )

    asset = native_asset(profile)
    native_amount = w3.eth.get_balance(address)
    balances: list[dict[str, Any]] = [
        {
            "type": "native",
            "denom": asset["denom"],
            "symbol": asset["symbol"],
            "decimals": asset["decimals"],
            "amount": str(native_amount),
            "display_amount": display_amount(native_amount, asset["decimals"]),
        }
    ]

    deployment_reference = required_string(
        chain, "deployment_file", f"chain {chain.get('name')}"
    )
    deployment = load_json(resolve_descriptor_path(deployment_reference, chains_path))
    if not isinstance(deployment, dict):
        raise BalanceError("Arquivo de deployment Besu deve ser um objeto")
    handler = required_string(deployment, "ibc_handler", "deployment Besu")
    ics20_address = required_string(deployment, "ics20_transfer", "deployment Besu")
    ics20 = w3.eth.contract(
        address=Web3.to_checksum_address(ics20_address),
        abi=[ICS20_BALANCE_ABI],
    )
    for denom in sorted(known_ics20_denoms(w3, handler)):
        amount = int(ics20.functions.balanceOf(address, denom).call())
        if amount:
            balances.append(
                {
                    "type": "ibc",
                    "contract": Web3.to_checksum_address(ics20_address),
                    "denom": denom,
                    "amount": str(amount),
                }
            )

    erc20_address = deployment.get("test_erc20")
    if isinstance(erc20_address, str) and erc20_address:
        token = w3.eth.contract(
            address=Web3.to_checksum_address(erc20_address),
            abi=ERC20_ABI,
        )
        amount = int(token.functions.balanceOf(address).call())
        if amount:
            decimals = int(token.functions.decimals().call())
            balances.append(
                {
                    "type": "erc20",
                    "contract": Web3.to_checksum_address(erc20_address),
                    "symbol": str(token.functions.symbol().call()),
                    "decimals": decimals,
                    "amount": str(amount),
                    "display_amount": display_amount(amount, decimals),
                }
            )
    return address, balances


def check_balance(chain_name: str, account_name: str) -> dict[str, Any]:
    logical_name, chain, account, profile, chains_path = load_context(
        chain_name, account_name
    )
    adapter = required_string(profile, "adapter", f"profile {profile.get('name')}")
    if adapter == "tendermint":
        address, balances = tendermint_balances(chain, account, profile)
    elif adapter == "ethereum":
        address, balances = ethereum_balances(
            chain, account, profile, chains_path
        )
    else:
        raise BalanceError(f"Adapter nao suportado: {adapter}")

    return {
        "chain": logical_name,
        "chain_id": required_string(chain, "chain_id", f"chain {logical_name}"),
        "adapter": adapter,
        "account": account_name,
        "address": address,
        "balances": balances,
    }


def main() -> int:
    args = parse_args()
    try:
        output = check_balance(args.chain, args.account)
    except (
        BalanceError,
        requests.RequestException,
        Web3Exception,
        ValueError,
    ) as exc:
        print(f"Falha: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
