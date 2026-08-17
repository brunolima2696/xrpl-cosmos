from pathlib import Path
import json
import subprocess


ROOT_DIR = Path(__file__).resolve().parents[1]
CHAINS_FILE = ROOT_DIR / "chains.json"

HERMES_CONTAINER = "hermes"
HD_PATH = "m/44'/60'/0'/0/0"


def load_chains():
    data = json.loads(CHAINS_FILE.read_text(encoding="utf-8"))
    return data["chains"]


def import_key(chain):
    chain_id = chain["chain_id"]
    key_name = chain["key_name"]
    mnemonic_file = f"/home/hermes/.hermes/mnemonics/{key_name}.txt"

    cmd = [
        "docker", "exec", HERMES_CONTAINER,
        "hermes", "keys", "add",
        "--chain", chain_id,
        "--mnemonic-file", mnemonic_file,
        "--key-name", key_name,
        "--hd-path", HD_PATH,
        "--overwrite",
    ]

    print(f"Importando {key_name} em {chain_id}...")
    subprocess.run(cmd, check=True)


def main():
    for chain in load_chains():
        import_key(chain)


if __name__ == "__main__":
    main()