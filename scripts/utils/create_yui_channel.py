import argparse

from yui_common import DEFAULT_PATH_CHAINS, cli_main, path_name, run_yui


def main():
    default = path_name(*DEFAULT_PATH_CHAINS)
    parser = argparse.ArgumentParser(description="Cria ou valida o IBC channel.")
    parser.add_argument("path", nargs="?", default=default)
    args = parser.parse_args()
    run_yui("tx", "channel", args.path)


if __name__ == "__main__":
    cli_main(main)
