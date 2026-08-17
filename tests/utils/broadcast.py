import os
import requests
from utils.chain_info import find_chain
from dotenv import load_dotenv

load_dotenv(override=True)


def get_account_info(address, chain_name):
    chain = find_chain(chain_name)
    port = chain["rest_port"]

    url = f"http://localhost:{port}/cosmos/auth/v1beta1/accounts/{address}"

    response = requests.get(url)
    data = response.json()

    account = data["account"]

    if "base_account" in account:
        account = account["base_account"]

    account_number = int(account["account_number"])
    sequence = int(account["sequence"])

    return account_number, sequence


def broadcast_tx(tx_raw_bytes, chain_name):
    chain = find_chain(chain_name)
    port = chain["rpc_port"]
    tx_hex = "0x" + tx_raw_bytes.hex()

    url = f"http://localhost:{port}/broadcast_tx_sync"

    response = requests.get(
        url,
        params={"tx": tx_hex},
    )

    return response.json()