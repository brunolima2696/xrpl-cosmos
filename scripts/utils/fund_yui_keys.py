import json
from decimal import Decimal

from bech32 import bech32_decode, bech32_encode, convertbits
import requests
from web3 import Web3

from yui_common import (
    ROOT_DIR,
    chain_funding_config,
    chain_yui_config,
    cli_main,
    run_yui,
    selected_chains_from_cli,
)


ACCOUNTS_FILE = ROOT_DIR / "accounts.json"


def read_alice():
    with ACCOUNTS_FILE.open(encoding="utf-8") as file:
        accounts = json.load(file)["accounts"]

    matches = [account for account in accounts if account.get("name") == "alice"]
    if len(matches) != 1:
        raise ValueError(
            "accounts.json deve conter exatamente uma conta com name=alice"
        )

    alice = matches[0]
    required_fields = ("chains", "evm_address", "private_key")
    missing = [field for field in required_fields if not alice.get(field)]
    if missing:
        raise ValueError(
            "Conta alice sem campos obrigatórios: " + ", ".join(missing)
        )
    return alice


def yui_key_address(chain):
    result = run_yui(
        "tendermint",
        "keys",
        "show",
        chain["chain_id"],
        chain["key_name"],
        capture=True,
    )
    return result.stdout.strip()


def decode_account_address(address):
    _, data = bech32_decode(address)
    if data is None:
        raise ValueError(f"Endereço Bech32 inválido: {address}")

    decoded = convertbits(data, 5, 8, False)
    if decoded is None or len(decoded) != 20:
        raise ValueError(f"Payload inválido no endereço: {address}")
    return bytes(decoded)


def encode_cosmos_address(prefix, address_bytes):
    data = convertbits(address_bytes, 8, 5, True)
    if data is None:
        raise ValueError("Não foi possível converter o endereço para Bech32")
    return bech32_encode(prefix, data)


def xrp_to_wei(amount):
    return int(amount * Decimal(10**18))


def fund_yui_key(chain, alice):
    if chain["name"] not in alice["chains"]:
        raise ValueError(
            f"A conta alice não pertence à chain {chain['name']}"
        )

    displayed_address = yui_key_address(chain)
    address_bytes = decode_account_address(displayed_address)
    account_prefix = chain_yui_config(chain)["account_prefix"]
    cosmos_address = encode_cosmos_address(account_prefix, address_bytes)
    evm_address = Web3.to_checksum_address("0x" + address_bytes.hex())

    rpc_url = f"http://localhost:{chain['evm_rpc_port']}"
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(f"Sem conexão com {chain['name']} em {rpc_url}")

    alice_address = Web3.to_checksum_address(alice["evm_address"])
    alice_private_key = alice["private_key"]
    target_xrp = Decimal(chain_funding_config(chain)["target_xrp"])
    target_balance = xrp_to_wei(target_xrp)
    current_balance = w3.eth.get_balance(evm_address)

    print(f"{chain['name']}: YUI {cosmos_address}")
    if current_balance >= target_balance:
        print(
            f"{chain['name']}: saldo já é de pelo menos "
            f"{target_xrp} XRP; financiamento ignorado"
        )
        return

    amount = target_balance - current_balance
    amount_xrp = Decimal(amount) / Decimal(10**18)
    tx = {
        "from": alice_address,
        "to": evm_address,
        "value": amount,
        "nonce": w3.eth.get_transaction_count(alice_address, "pending"),
        "gas": 21000,
        "gasPrice": w3.eth.gas_price,
        "chainId": w3.eth.chain_id,
    }
    signed = w3.eth.account.sign_transaction(tx, alice_private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    print(f"{chain['name']}: enviando {amount_xrp} XRP para {evm_address}")
    print(f"{chain['name']}: tx {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError(f"Transação falhou: {tx_hash.hex()}")
    print(f"{chain['name']}: confirmado no bloco {receipt.blockNumber}")


def validate_prefunded_yui_key(chain):
    address = yui_key_address(chain)
    funding = chain_funding_config(chain)
    expected_prefix = chain_yui_config(chain)["account_prefix"]
    actual_prefix, data = bech32_decode(address)
    if data is None or actual_prefix != expected_prefix:
        raise ValueError(
            f"Endereço YUI inválido para {chain['name']}: esperado prefixo "
            f"{expected_prefix}, recebido {address}"
        )

    denom = funding["denom"]
    minimum_balance = int(funding.get("minimum_balance", "1"))
    url = (
        f"http://127.0.0.1:{chain['rest_port']}"
        f"/cosmos/bank/v1beta1/balances/{address}/by_denom"
    )
    response = requests.get(url, params={"denom": denom}, timeout=10)
    response.raise_for_status()
    balance = int((response.json().get("balance") or {}).get("amount", "0"))

    print(f"{chain['name']}: YUI {address}")
    print(f"{chain['name']}: saldo {balance}{denom}")
    if balance < minimum_balance:
        raise RuntimeError(
            f"Relayer de {chain['name']} sem saldo suficiente: "
            f"mínimo {minimum_balance}{denom}"
        )
    print(f"{chain['name']}: saldo pré-financiado validado.")


def main():
    chains = selected_chains_from_cli(
        "Financia as chaves YUI das chains selecionadas."
    )
    needs_alice = any(
        chain_funding_config(chain)["mode"] == "evm-transfer"
        for chain in chains
    )
    alice = read_alice() if needs_alice else None

    for chain in chains:
        mode = chain_funding_config(chain)["mode"]
        if mode == "evm-transfer":
            fund_yui_key(chain, alice)
        elif mode == "balance-check":
            validate_prefunded_yui_key(chain)
        else:
            raise ValueError(f"Modo de funding não suportado: {mode}")


if __name__ == "__main__":
    cli_main(main)
