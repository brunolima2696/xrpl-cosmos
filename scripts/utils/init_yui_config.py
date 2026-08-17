from yui_common import YUI_HOME, cli_main, run_yui


def main():
    YUI_HOME.mkdir(parents=True, exist_ok=True)
    run_yui("config", "init")
    print("Configuração global do YUI inicializada.")


if __name__ == "__main__":
    cli_main(main)
