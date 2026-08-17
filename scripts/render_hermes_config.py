from pathlib import Path
import json


ROOT_DIR = Path(__file__).resolve().parents[1]
CHAINS_FILE = ROOT_DIR / "chains.json"
OUTPUT_FILE = ROOT_DIR / "relayer_config" / "hermes" / "config.toml"
MNEMONICS_DIR = ROOT_DIR / "relayer_config" / "hermes" / "mnemonics"



def load_chains():
    data = json.loads(CHAINS_FILE.read_text(encoding="utf-8"))
    return data["chains"]


def render_chain(chain):
    chain_id = chain["chain_id"]
    ip = chain["ip"]
    key_name = chain["key_name"]

    return f"""
[[chains]]
id = {json.dumps(str(chain_id))}
type = "CosmosSdk"
rpc_addr = "http://{ip}:26657"
grpc_addr = "http://{ip}:9090"
event_source = {{ mode = "push", url = "ws://{ip}:26657/websocket", batch_delay = "500ms" }}
rpc_timeout = "10s"
trusted_node = true
account_prefix = "ethm"
key_name = {json.dumps(str(key_name))}
key_store_folder = "/home/hermes/.hermes/keys"
address_type = {{ derivation = "ethermint", proto_type = {{ pk_type = "/ethermint.crypto.v1.ethsecp256k1.PubKey" }} }}
store_prefix = "ibc"
default_gas = 100000
max_gas = 4000000
gas_price = {{ price = 1, denom = "axrp" }}
gas_multiplier = 1.2
max_msg_num = 30
max_tx_size = 2097152
clock_drift = "5s"
max_block_time = "30s"
trusting_period = "43200s"
trust_threshold = "2/3"

[chains.packet_filter]
policy = "allow"
list = [
  ["transfer", "*"],
]
"""


def write_mnemonics(chains):
    MNEMONICS_DIR.mkdir(parents=True, exist_ok=True)

    for chain in chains:
        mnemonic_file = MNEMONICS_DIR / f"{chain['key_name']}.txt"
        mnemonic_file.write_text(chain["relayer_mnemonic"].strip() + "\n", encoding="utf-8")


def render_config():
    chains = load_chains()

    write_mnemonics(chains)

    chain_blocks = "".join(render_chain(chain) for chain in chains)

    content = f"""[global]
log_level = "info"

[mode]

[mode.clients]
enabled = true
refresh = true
misbehaviour = false

[mode.connections]
enabled = true

[mode.channels]
enabled = true

[mode.packets]
enabled = true
clear_interval = 100
clear_on_start = true
tx_confirmation = false

[rest]
enabled = false
host = "0.0.0.0"
port = 3000

[telemetry]
enabled = false
host = "0.0.0.0"
port = 3001
{chain_blocks}
"""

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    render_config()
    print(f"Config: {OUTPUT_FILE}")
    print(f"Mnemonics: {MNEMONICS_DIR}")
