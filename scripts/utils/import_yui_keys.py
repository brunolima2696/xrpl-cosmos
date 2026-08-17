from yui_common import cli_main, run_yui, selected_chains_from_cli


def import_key(chain):
    chain_id = chain["chain_id"]
    key_name = chain["key_name"]
    mnemonic = chain["relayer_mnemonic"].strip()

    print(f"Importando {key_name} em {chain_id}...")
    result = run_yui(
        "tendermint",
        "keys",
        "restore",
        chain_id,
        key_name,
        mnemonic,
        capture=True,
        check=False,
    )

    output = "\n".join((result.stdout, result.stderr)).strip()
    if result.returncode == 0:
        print(f"Importada: {key_name} -> {result.stdout.strip()}")
        return

    if f"a key with name {key_name} already exists" in output:
        show_result = run_yui(
            "tendermint",
            "keys",
            "show",
            chain_id,
            key_name,
            capture=True,
        )
        print(f"Já existente: {key_name} -> {show_result.stdout.strip()}")
        return

    if output:
        print(output)
    raise RuntimeError(f"Falha ao importar {key_name} em {chain_id}")


def main():
    chains = selected_chains_from_cli(
        "Importa no YUI as chaves das chains selecionadas."
    )
    for chain in chains:
        import_key(chain)


if __name__ == "__main__":
    cli_main(main)
