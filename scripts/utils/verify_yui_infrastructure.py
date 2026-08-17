import time

import requests

from yui_common import CONTAINER, cli_main, run, selected_chains_from_cli


def main():
    chains = selected_chains_from_cli(
        "Verifica o YUI e os RPCs das chains selecionadas."
    )
    container = run(
        ["docker", "inspect", "--format", "{{.State.Running}}", CONTAINER],
        capture=True,
    )
    if container.stdout.strip().lower() != "true":
        raise RuntimeError(f"O container {CONTAINER} não está em execução")

    deadline = time.monotonic() + 120
    pending = {chain["chain_id"]: chain for chain in chains}
    while pending and time.monotonic() < deadline:
        for chain_id, chain in list(pending.items()):
            try:
                response = requests.get(
                    f"http://127.0.0.1:{chain['rpc_port']}/status", timeout=3
                )
                response.raise_for_status()
                result = response.json()["result"]
                network = result["node_info"]["network"]
                catching_up = result["sync_info"]["catching_up"]
                if network == chain_id and not catching_up:
                    del pending[chain_id]
            except (KeyError, ValueError, requests.RequestException):
                pass
        if pending:
            time.sleep(2)

    if pending:
        raise RuntimeError(
            "RPCs indisponíveis ou ainda sincronizando: " + ", ".join(pending)
        )

    names = ", ".join(chain["name"] for chain in chains)
    print(f"Container YUI e RPCs disponíveis para: {names}.")


if __name__ == "__main__":
    cli_main(main)
