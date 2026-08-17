from pathlib import Path
import json
import subprocess
import sys
import urllib.request


ROOT_DIR = Path(__file__).resolve().parents[1]
CHAINS_FILE = ROOT_DIR / "chains.json"

HERMES_CONTAINER = "hermes"
PORT_ID = "transfer"


def load_chains_data():
    return json.loads(CHAINS_FILE.read_text(encoding="utf-8"))


def save_chains_data(data):
    CHAINS_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def find_chain(chains, label):
    for chain in chains:
        if chain["label"] == label or chain["name"] == label or chain["chain_id"] == label:
            return chain

    raise ValueError(f"Chain não encontrada: {label}")


def get_channels(chain):
    url = f"http://localhost:{chain['rest_port']}/ibc/core/channel/v1/channels"

    with urllib.request.urlopen(url) as response:
        data = json.loads(response.read().decode("utf-8"))

    channels = {}

    for channel in data.get("channels", []):
        if channel.get("port_id") == PORT_ID:
            channels[channel["channel_id"]] = channel

    return channels


def create_channel(source_chain, destination_chain):
    cmd = [
        "docker", "exec", HERMES_CONTAINER,
        "hermes", "create", "channel",
        "--a-chain", source_chain["chain_id"],
        "--b-chain", destination_chain["chain_id"],
        "--a-port", PORT_ID,
        "--b-port", PORT_ID,
        "--new-client-connection",
        "--yes",
    ]

    subprocess.run(cmd, check=True)


def get_new_channel(before, after):
    before_ids = set(before.keys())
    after_ids = set(after.keys())

    new_ids = list(after_ids - before_ids)

    if len(new_ids) != 1:
        raise RuntimeError(f"Não foi possível identificar canal novo. Novos canais: {new_ids}")

    return new_ids[0]


def open_ibc_channel(source_label, destination_label):
    data = load_chains_data()
    chains = data["chains"]

    source_chain = find_chain(chains, source_label)
    destination_chain = find_chain(chains, destination_label)

    source_before = get_channels(source_chain)
    destination_before = get_channels(destination_chain)

    create_channel(source_chain, destination_chain)

    source_after = get_channels(source_chain)
    destination_after = get_channels(destination_chain)

    source_channel_id = get_new_channel(source_before, source_after)
    destination_channel_id = get_new_channel(destination_before, destination_after)

    source_chain.setdefault("channels", {})
    destination_chain.setdefault("channels", {})

    source_chain["channels"][destination_chain["label"]] = source_channel_id
    destination_chain["channels"][source_chain["label"]] = destination_channel_id

    save_chains_data(data)

    print(f"{source_chain['label']} -> {destination_chain['label']}: {source_channel_id}")
    print(f"{destination_chain['label']} -> {source_chain['label']}: {destination_channel_id}")
    print(f"Atualizado: {CHAINS_FILE}")


if __name__ == "__main__":
    open_ibc_channel(sys.argv[1], sys.argv[2])