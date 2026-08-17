from pathlib import Path
from decimal import Decimal
import json
import os

from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3


ROOT_DIR = Path(__file__).resolve().parents[1]
CHAINS_FILE = ROOT_DIR / "chains.json"
ENV_FILE = ROOT_DIR / ".env"

FUND_AMOUNT_XRP = Decimal("100")
DERIVATION_PATH = "m/44'/60'/0'/0/0"


def load_chains():
    data = json.loads(CHAINS_FILE.read_text(encoding="utf-8"))
    return data["chains"]


def xrp_to_wei(amount):
    return int(amount * Decimal(10**18))


def relayer_address_from_mnemonic(mnemonic):
    Account.enable_unaudited_hdwallet_features()

    account = Account.from_mnemonic(
        mnemonic.strip(),
        account_path=DERIVATION_PATH,
    )

    return Web3.to_checksum_address(account.address)


def fund_relayer(chain):
    rpc_url = f"http://localhost:{chain['evm_rpc_port']}"
    w3 = Web3(Web3.HTTPProvider(rpc_url))

    alice_address = Web3.to_checksum_address(os.environ["ALICE_EVM_ADDRESS"])
    alice_private_key = os.environ["ALICE_PRIVATE_KEY"]

    relayer_address = relayer_address_from_mnemonic(chain["relayer_mnemonic"])
    value = xrp_to_wei(FUND_AMOUNT_XRP)

    tx = {
        "from": alice_address,
        "to": relayer_address,
        "value": value,
        "nonce": w3.eth.get_transaction_count(alice_address, "pending"),
        "gas": 21000,
        "gasPrice": w3.eth.gas_price,
        "chainId": w3.eth.chain_id,
    }

    signed = w3.eth.account.sign_transaction(tx, alice_private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    print(f"{chain['label']}: enviando 100 XRP para {relayer_address}")
    print(f"{chain['label']}: tx {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    print(f"{chain['label']}: confirmado no bloco {receipt.blockNumber}")


def main():
    load_dotenv(ENV_FILE)

    for chain in load_chains():
        fund_relayer(chain)


if __name__ == "__main__":
    main()
