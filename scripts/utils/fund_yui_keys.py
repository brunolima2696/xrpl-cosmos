import os
from decimal import Decimal

from bech32 import bech32_decode, bech32_encode, convertbits
from dotenv import load_dotenv
from web3 import Web3

from yui_common import ROOT_DIR, cli_main, run_yui, selected_chains_from_cli


ENV_FILE = ROOT_DIR / ".env"
TARGET_BALANCE_XRP = Decimal("100")
BECH32_PREFIX = "ethm"


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


def encode_cosmos_address(address_bytes):
    data = convertbits(address_bytes, 8, 5, True)
    if data is None:
        raise ValueError("Não foi possível converter o endereço para Bech32")
    return bech32_encode(BECH32_PREFIX, data)


def xrp_to_wei(amount):
    return int(amount * Decimal(10**18))


def fund_yui_key(chain):
    displayed_address = yui_key_address(chain)
    address_bytes = decode_account_address(displayed_address)
    cosmos_address = encode_cosmos_address(address_bytes)
    evm_address = Web3.to_checksum_address("0x" + address_bytes.hex())

    rpc_url = f"http://localhost:{chain['evm_rpc_port']}"
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(f"Sem conexão com {chain['label']} em {rpc_url}")

    alice_address = Web3.to_checksum_address(os.environ["ALICE_EVM_ADDRESS"])
    alice_private_key = os.environ["ALICE_PRIVATE_KEY"]
    target_balance = xrp_to_wei(TARGET_BALANCE_XRP)
    current_balance = w3.eth.get_balance(evm_address)

    print(f"{chain['label']}: YUI {cosmos_address}")
    if current_balance >= target_balance:
        print(
            f"{chain['label']}: saldo já é de pelo menos "
            f"{TARGET_BALANCE_XRP} XRP; financiamento ignorado"
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

    print(f"{chain['label']}: enviando {amount_xrp} XRP para {evm_address}")
    print(f"{chain['label']}: tx {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    if receipt.status != 1:
        raise RuntimeError(f"Transação falhou: {tx_hash.hex()}")
    print(f"{chain['label']}: confirmado no bloco {receipt.blockNumber}")


def main():
    load_dotenv(ENV_FILE)
    chains = selected_chains_from_cli(
        "Financia as chaves YUI das chains selecionadas."
    )
    for chain in chains:
        fund_yui_key(chain)


if __name__ == "__main__":
    cli_main(main)
