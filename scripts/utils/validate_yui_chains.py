from yui_common import (
    chain_mnemonic,
    chain_template,
    cli_main,
    selected_chains_from_cli,
)


def main():
    chains = selected_chains_from_cli(
        "Valida os metadados das chains antes de configurar o YUI."
    )
    for chain in chains:
        chain_mnemonic(chain)
        chain_template(chain)
        print(f"Metadados válidos: {chain['name']}")


if __name__ == "__main__":
    cli_main(main)
