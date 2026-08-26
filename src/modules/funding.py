import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from .errors import FundingError
from .models import BlockchainConfig, Chain


def _load_web3():
    try:
        from web3 import Web3
    except ModuleNotFoundError as exc:
        raise FundingError(
            "Dependencia web3 nao instalada; execute pip install -r requirements.txt"
        ) from exc
    return Web3


def _read_accounts(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FundingError(f"Arquivo de contas nao encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise FundingError(
            f"JSON invalido em {path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc

    accounts = document.get("accounts") if isinstance(document, dict) else None
    if not isinstance(accounts, list):
        raise FundingError(f"{path}: accounts deve ser uma lista")
    if not all(isinstance(account, dict) for account in accounts):
        raise FundingError(f"{path}: todas as contas devem ser objetos")
    return tuple(accounts)


def _required_account_field(account: dict[str, Any], field: str, context: str) -> Any:
    value = account.get(field)
    if value is None or value == "":
        raise FundingError(f"{context}: campo obrigatorio ausente: {field}")
    return value


def _alice(config_dir: Path) -> dict[str, Any]:
    accounts = _read_accounts(config_dir / "user-accounts.json")
    matches = [account for account in accounts if account.get("name") == "alice"]
    if len(matches) != 1:
        raise FundingError(
            "user-accounts.json deve conter exatamente uma conta name=alice"
        )
    alice = matches[0]
    context = "conta alice"
    for field in ("chains", "evm_address", "private_key"):
        _required_account_field(alice, field, context)
    if not isinstance(alice["chains"], list):
        raise FundingError("conta alice: chains deve ser uma lista")
    return alice


def _relayers_by_chain(
    config_dir: Path,
    chains: tuple[Chain, ...],
) -> dict[str, tuple[dict[str, Any], ...]]:
    accounts = _read_accounts(config_dir / "relayer-accounts.json")
    result: dict[str, tuple[dict[str, Any], ...]] = {}
    for chain in chains:
        matches = []
        for account in accounts:
            memberships = account.get("chains")
            if not isinstance(memberships, list):
                raise FundingError(
                    f"conta {account.get('name', '<sem nome>')}: chains deve ser uma lista"
                )
            if chain.name not in memberships:
                continue
            context = f"relayer de {chain.name}"
            _required_account_field(account, "name", context)
            _required_account_field(account, "evm_address", context)
            matches.append(account)
        if not matches:
            raise FundingError(f"Nenhum relayer declarado para {chain.name}")
        result[chain.name] = tuple(matches)
    return result


def xrp_to_base_units(amount: Decimal, decimals: int) -> int:
    scaled = amount * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise FundingError(
            f"Quantidade possui mais de {decimals} casas decimais: {amount}"
        )
    return int(scaled)


def _native_decimals(config: BlockchainConfig) -> int:
    native_asset = config.profile.get("native_asset")
    if not isinstance(native_asset, dict):
        raise FundingError("profile.json: native_asset deve ser um objeto")
    value = native_asset.get("decimals")
    if isinstance(value, bool):
        raise FundingError("profile.json: native_asset.decimals invalido")
    try:
        decimals = int(value)
    except (TypeError, ValueError) as exc:
        raise FundingError("profile.json: native_asset.decimals invalido") from exc
    if decimals < 0:
        raise FundingError("profile.json: native_asset.decimals nao pode ser negativo")
    return decimals


def _fund_chain(
    chain: Chain,
    alice: dict[str, Any],
    relayers: tuple[dict[str, Any], ...],
    value: int,
    amount: Decimal,
    web3_class=None,
) -> None:
    if chain.name not in alice["chains"]:
        raise FundingError(f"A conta alice nao pertence a {chain.name}")

    rpc_url = f"http://127.0.0.1:{chain.ports.evm_rpc}"
    web3_class = web3_class or _load_web3()
    web3 = web3_class(web3_class.HTTPProvider(rpc_url))
    if not web3.is_connected():
        raise FundingError(f"Sem conexao EVM com {chain.name} em {rpc_url}")

    try:
        sender = web3_class.to_checksum_address(alice["evm_address"])
        nonce = web3.eth.get_transaction_count(sender, "pending")
        gas_price = web3.eth.gas_price
        evm_chain_id = web3.eth.chain_id

        for offset, relayer in enumerate(relayers):
            receiver = web3_class.to_checksum_address(relayer["evm_address"])
            transaction = {
                "from": sender,
                "to": receiver,
                "value": value,
                "nonce": nonce + offset,
                "gas": 21000,
                "gasPrice": gas_price,
                "chainId": evm_chain_id,
            }
            signed = web3.eth.account.sign_transaction(
                transaction,
                alice["private_key"],
            )
            tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
            print(
                f"{chain.name}: enviando {amount} XRP para "
                f"{relayer['name']} ({receiver})"
            )
            print(f"{chain.name}: tx {tx_hash.hex()}")

            receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
            if receipt.status != 1:
                raise FundingError(
                    f"{chain.name}: transacao falhou: {tx_hash.hex()}"
                )
            print(f"{chain.name}: confirmado no bloco {receipt.blockNumber}")
    except FundingError:
        raise
    except Exception as exc:
        raise FundingError(f"Falha ao financiar relayers de {chain.name}: {exc}") from exc


def _validate_funding_plan(
    chains: tuple[Chain, ...],
    alice: dict[str, Any],
    relayers: dict[str, tuple[dict[str, Any], ...]],
    web3_class,
) -> None:
    try:
        web3_class.to_checksum_address(alice["evm_address"])
    except Exception as exc:
        raise FundingError("conta alice: evm_address invalido") from exc

    for chain in chains:
        if chain.name not in alice["chains"]:
            raise FundingError(f"A conta alice nao pertence a {chain.name}")
        for relayer in relayers[chain.name]:
            try:
                web3_class.to_checksum_address(relayer["evm_address"])
            except Exception as exc:
                raise FundingError(
                    f"{relayer['name']}: evm_address invalido para {chain.name}"
                ) from exc


def fund_relayers(
    config: BlockchainConfig,
    chains: tuple[Chain, ...],
    amount: Decimal,
) -> None:
    alice = _alice(config.config_dir)
    relayers = _relayers_by_chain(config.config_dir, chains)
    value = xrp_to_base_units(amount, _native_decimals(config))
    web3_class = _load_web3()
    _validate_funding_plan(chains, alice, relayers, web3_class)

    for chain in chains:
        _fund_chain(
            chain,
            alice,
            relayers[chain.name],
            value,
            amount,
            web3_class,
        )
