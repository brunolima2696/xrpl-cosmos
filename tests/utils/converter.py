from bech32 import bech32_encode, convertbits
from eth_keys import keys
from dotenv import load_dotenv
load_dotenv()

BECH32_PREFIX = "ethm"


def get_private_key(private_key: str):
    return keys.PrivateKey(bytes.fromhex(private_key))


def get_compressed_pubkey(private_key):
    public_key_bytes = private_key.public_key.to_bytes()

    x = public_key_bytes[:32]
    y = public_key_bytes[32:]

    y_int = int.from_bytes(y, "big")
    prefix = b"\x02" if y_int % 2 == 0 else b"\x03"

    return prefix + x


def evm_address_to_cosmos_address(evm_address_bytes):
    converted = convertbits(evm_address_bytes, 8, 5)

    return bech32_encode(BECH32_PREFIX, converted)


def get_user_cosmos_address(private_key):
    evm_address_bytes = private_key.public_key.to_canonical_address()

    return evm_address_to_cosmos_address(evm_address_bytes)