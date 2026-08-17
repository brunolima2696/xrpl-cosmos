from yui_common import (
    CHAIN_CONFIG_DIR,
    chain_template,
    cli_main,
    selected_chains_from_cli,
    write_json,
)


def main():
    chains = selected_chains_from_cli(
        "Gera os arquivos de configuração das chains selecionadas."
    )
    for chain in chains:
        destination = CHAIN_CONFIG_DIR / f"{chain['name']}.json"
        write_json(destination, chain_template(chain))
        print(f"Gerado: {destination}")


if __name__ == "__main__":
    cli_main(main)
