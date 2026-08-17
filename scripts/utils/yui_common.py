import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
CHAINS_FILE = ROOT_DIR / "chains.json"
YUI_HOME = ROOT_DIR / "relayer_config" / "yui"
CHAIN_CONFIG_DIR = YUI_HOME / "chains"
PATH_CONFIG_DIR = YUI_HOME / "paths"
CONTAINER = "yui-relayer"

DEFAULT_PATH_CHAINS = ("xrplevm-a", "xrplevm-b")


def run(command, *, capture=False, check=True):
    result = subprocess.run(
        command,
        cwd=ROOT_DIR,
        text=True,
        capture_output=capture,
        check=False,
    )
    if check and result.returncode != 0:
        if capture:
            if result.stdout:
                print(result.stdout.rstrip(), file=sys.stderr)
            if result.stderr:
                print(result.stderr.rstrip(), file=sys.stderr)
        raise RuntimeError(
            f"Comando falhou com código {result.returncode}: {' '.join(command)}"
        )
    return result


def run_yui(*arguments, capture=False, check=True):
    return run(
        ["docker", "exec", CONTAINER, "yrly", *arguments],
        capture=capture,
        check=check,
    )


def cli_main(function):
    try:
        function()
    except KeyboardInterrupt:
        print("Operação interrompida pelo usuário.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f"Falha: {error}", file=sys.stderr)
        raise SystemExit(1)


def read_chains():
    with CHAINS_FILE.open(encoding="utf-8") as file:
        chains = json.load(file)["chains"]

    required_fields = (
        "name",
        "service",
        "chain_id",
        "rpc_port",
        "evm_rpc_port",
        "key_name",
        "relayer_mnemonic",
    )
    for chain in chains:
        missing = [field for field in required_fields if not chain.get(field)]
        if missing:
            raise ValueError(
                f"Chain {chain.get('name', '<sem nome>')} sem campos: "
                + ", ".join(missing)
            )
    return chains


def select_chains(names):
    chains = read_chains()
    if not names:
        return chains

    chains_by_name = {chain["name"]: chain for chain in chains}
    missing = [name for name in names if name not in chains_by_name]
    if missing:
        raise ValueError(
            "Chains não encontradas no chains.json: " + ", ".join(missing)
        )
    return [chains_by_name[name] for name in dict.fromkeys(names)]


def selected_chains_from_cli(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "chains",
        nargs="*",
        metavar="CHAIN",
        help="nomes das chains; sem valores, processa todas",
    )
    return select_chains(parser.parse_args().chains)


def yui_config():
    result = run_yui("config", "show", capture=True)
    return json.loads(result.stdout)


def chain_template(chain):
    return {
        "chain": {
            "@type": "/relayer.chains.tendermint.config.ChainConfig",
            "key": chain["key_name"],
            "chain_id": chain["chain_id"],
            "rpc_addr": f"http://{chain['service']}:26657",
            "account_prefix": "ethm",
            "gas_adjustment": 1.5,
            "gas_prices": "1axrp",
            "average_block_time_msec": 5000,
            "max_retry_for_commit": 10,
        },
        "prover": {
            "@type": "/relayer.chains.tendermint.config.ProverConfig",
            "trusting_period": "12h",
            "refresh_threshold_rate": {
                "numerator": 2,
                "denominator": 3,
            },
        },
    }


def path_name(source_name, destination_name):
    prefix = "xrplevm-"
    if source_name.startswith(prefix) and destination_name.startswith(prefix):
        return (
            f"{prefix}{source_name.removeprefix(prefix)}-"
            f"{destination_name.removeprefix(prefix)}"
        )
    return f"{source_name}-{destination_name}"


def path_template(source, destination):
    endpoint_defaults = {
        "client-id": "",
        "connection-id": "",
        "channel-id": "",
        "port-id": "transfer",
        "order": "unordered",
        "version": "ics20-1",
    }
    return {
        "src": {"chain-id": source["chain_id"], **endpoint_defaults},
        "dst": {"chain-id": destination["chain_id"], **endpoint_defaults},
        "strategy": {"type": "naive"},
    }


def write_json(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(content, file, ensure_ascii=False, indent=2)
        file.write("\n")
