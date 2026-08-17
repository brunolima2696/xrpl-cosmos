import json

CHAINS_FILE = "chains.json"

def load_chains():
    with open(CHAINS_FILE, "r", encoding="utf-8") as file:
        return json.load(file)["chains"]


def find_chain(chain_name):
    chains = load_chains()

    for chain in chains:
        identifiers = [
            chain.get("name"),
            chain.get("service"),
            chain.get("chain_id"),
        ]

        if chain_name in identifiers:
            return chain

    raise ValueError(f"Chain não encontrada no chains.json: {chain_name}")
