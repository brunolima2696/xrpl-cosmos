from bip_utils import (
    Bip39SeedGenerator,
    Bip44,
    Bip44Coins,
    Bip44Changes,
    EthAddrEncoder,
    Bech32Encoder,
)

MNEMONIC = "scheme spot photo card baby mountain device kick cradle pact join borrow"

ACCOUNT_INDEX = 0
ADDRESS_INDEX = 0
COSMOS_PREFIX = "ethm"

seed_bytes = Bip39SeedGenerator(MNEMONIC).Generate()

wallet = (
    Bip44.FromSeed(seed_bytes, Bip44Coins.ETHEREUM)
    .Purpose()
    .Coin()
    .Account(ACCOUNT_INDEX)
    .Change(Bip44Changes.CHAIN_EXT)
    .AddressIndex(ADDRESS_INDEX)
)

private_key = wallet.PrivateKey().Raw().ToHex()
public_key = wallet.PublicKey().RawUncompressed().ToBytes()

evm_address = EthAddrEncoder.EncodeKey(public_key)
cosmos_address = Bech32Encoder.Encode(COSMOS_PREFIX, bytes.fromhex(evm_address[2:]))

print("HD path:", f"m/44'/60'/{ACCOUNT_INDEX}'/0/{ADDRESS_INDEX}")
print("EVM address:", evm_address)
print("Cosmos address:", cosmos_address)
print("Private key:", "0x" + private_key)