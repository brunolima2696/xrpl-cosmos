import argparse

from yui_common import DEFAULT_PATH_CHAINS, cli_main, path_name, yui_config


def main():
    default = path_name(*DEFAULT_PATH_CHAINS)
    parser = argparse.ArgumentParser(description="Valida um path configurado no YUI.")
    parser.add_argument("path", nargs="?", default=default)
    args = parser.parse_args()

    path = yui_config().get("paths", {}).get(args.path)
    if not path:
        raise RuntimeError(f"Path {args.path} não encontrado ao finalizar")

    print(f"Path: {args.path}")
    for label in ("src", "dst"):
        endpoint = path[label]
        fields = (
            endpoint.get("client-id"),
            endpoint.get("connection-id"),
            endpoint.get("channel-id"),
        )
        if not all(fields):
            raise RuntimeError(f"Endpoint {label} está incompleto: {endpoint}")
        print(
            f"{label}: chain={endpoint.get('chain-id')} "
            f"client={fields[0]} connection={fields[1]} channel={fields[2]}"
        )


if __name__ == "__main__":
    cli_main(main)
