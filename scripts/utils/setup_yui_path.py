import argparse

from yui_common import (
    DEFAULT_PATH_CHAINS,
    PATH_CONFIG_DIR,
    cli_main,
    configured_chain_ids,
    path_name,
    path_template,
    select_chains,
    run_yui,
    write_json,
    yui_config,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Gera e registra um path entre duas chains."
    )
    parser.add_argument("source", nargs="?", help="nome da chain de origem")
    parser.add_argument("destination", nargs="?", help="nome da chain de destino")
    args = parser.parse_args()
    if (args.source is None) != (args.destination is None):
        parser.error("informe as duas chains ou nenhuma")
    return (
        (args.source, args.destination)
        if args.source is not None
        else DEFAULT_PATH_CHAINS
    )


def main():
    source_name, destination_name = parse_args()
    if source_name == destination_name:
        raise ValueError("As chains de origem e destino devem ser diferentes")

    source, destination = select_chains([source_name, destination_name])
    name = path_name(source_name, destination_name)
    content = path_template(source, destination)
    path_file = PATH_CONFIG_DIR / f"{name}.json"
    write_json(path_file, content)

    config = yui_config()
    registered_chain_ids = configured_chain_ids(config)
    required_chain_ids = {source["chain_id"], destination["chain_id"]}
    missing_chain_ids = required_chain_ids - registered_chain_ids
    if missing_chain_ids:
        raise RuntimeError(
            "Chains ainda não registradas no YUI: " + ", ".join(missing_chain_ids)
        )

    configured_path = config.get("paths", {}).get(name)
    if configured_path:
        expected_ids = (content["src"]["chain-id"], content["dst"]["chain-id"])
        actual_ids = (
            configured_path["src"]["chain-id"],
            configured_path["dst"]["chain-id"],
        )
        if actual_ids != expected_ids:
            raise RuntimeError(
                f"O path {name} já existe para chains diferentes: {actual_ids}"
            )
        print(f"Path {name} já registrado; etapa ignorada.")
        return

    run_yui(
        "paths",
        "add",
        source["chain_id"],
        destination["chain_id"],
        name,
        f"--file=/root/.yui-relayer/paths/{name}.json",
    )


if __name__ == "__main__":
    cli_main(main)
