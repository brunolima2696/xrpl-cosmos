import shutil

from yui_common import cli_main, run, selected_chains_from_cli


NETWORK_SCRIPT = "scripts/connect-cosmos-network.sh"


def main():
    chains = selected_chains_from_cli(
        "Conecta ao YUI as chains executadas em redes Docker externas."
    )
    external_chains = [chain for chain in chains if chain.get("external_network")]
    if not external_chains:
        print("Nenhuma chain externa precisa ser conectada.")
        return

    bash = shutil.which("bash")
    if not bash:
        raise RuntimeError("bash não encontrado para executar o script de rede")

    for chain in external_chains:
        network = chain["external_network"]
        network_name = network["name"]
        alias = network.get("alias", chain["service"])
        run(
            [
                bash,
                NETWORK_SCRIPT,
                chain["service"],
                network_name,
                alias,
            ]
        )


if __name__ == "__main__":
    cli_main(main)
