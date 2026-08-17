from yui_common import cli_main, run_yui, selected_chains_from_cli


def main():
    chains = selected_chains_from_cli(
        "Inicializa os light clients locais das chains selecionadas."
    )
    for chain in chains:
        chain_id = chain["chain_id"]
        probe = run_yui(
            "tendermint",
            "light",
            "header",
            chain_id,
            "0",
            capture=True,
            check=False,
        )
        if probe.returncode == 0:
            print(f"Light client local de {chain_id} já inicializado.")
            continue
        run_yui("tendermint", "light", "init", chain_id, "-f")


if __name__ == "__main__":
    cli_main(main)
