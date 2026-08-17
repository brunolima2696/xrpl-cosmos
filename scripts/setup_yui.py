import argparse
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
UTILS_DIR = ROOT_DIR / "scripts" / "utils"
sys.path.insert(0, str(UTILS_DIR))

from yui_common import DEFAULT_PATH_CHAINS, path_name  # noqa: E402


CONFIG_STAGES = (
    ("gerar os arquivos de configuração das chains", "render_yui_chains.py"),
    ("registrar as chains no YUI", "add_yui_chains.py"),
    ("importar as chaves do relayer", "import_yui_keys.py"),
    ("financiar as chaves do relayer", "fund_yui_keys.py"),
    ("inicializar os light clients locais", "init_yui_light_clients.py"),
)


def timestamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


@contextmanager
def stage(name):
    started_at = time.monotonic()
    print(f"[{timestamp()}] INÍCIO: {name}", flush=True)
    try:
        yield
    except Exception:
        elapsed = time.monotonic() - started_at
        print(f"[{timestamp()}] ERRO: {name} ({elapsed:.1f}s)", flush=True)
        raise
    else:
        elapsed = time.monotonic() - started_at
        print(f"[{timestamp()}] FIM: {name} ({elapsed:.1f}s)", flush=True)


def run_script(filename, *arguments):
    script = UTILS_DIR / filename
    result = subprocess.run(
        [sys.executable, str(script), *arguments],
        cwd=ROOT_DIR,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"{filename} terminou com código {result.returncode}"
        )


def run_stage(name, filename, *arguments):
    with stage(name):
        run_script(filename, *arguments)


def configure_chains(chain_names):
    run_stage(
        "inicializar a configuração global do YUI",
        "init_yui_config.py",
    )
    for name, filename in CONFIG_STAGES:
        run_stage(name, filename, *chain_names)


def configure_path(source, destination):
    name = path_name(source, destination)
    run_stage(
        f"gerar e registrar o path {name}",
        "setup_yui_path.py",
        source,
        destination,
    )
    run_stage(
        f"criar ou validar os IBC clients de {name}",
        "create_yui_clients.py",
        name,
    )
    run_stage(
        f"criar ou validar a IBC connection de {name}",
        "create_yui_connection.py",
        name,
    )
    run_stage(
        f"criar ou validar o IBC channel de {name}",
        "create_yui_channel.py",
        name,
    )
    run_stage(
        f"validar o path {name}",
        "validate_yui_setup.py",
        name,
    )
    return name


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Configura chains e paths do YUI Relayer. Sem opções, configura "
            "todas as chains e o path xrplevm-a <-> xrplevm-b."
        )
    )
    parser.add_argument(
        "--config",
        metavar="CHAIN",
        help="configura somente a chain informada",
    )
    parser.add_argument(
        "--path",
        nargs=2,
        metavar=("SOURCE", "DESTINATION"),
        help="registra e configura um path entre duas chains",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    default_run = args.config is None and args.path is None

    configure_chain_names = []
    if args.config:
        configure_chain_names = [args.config]

    selected_path = None
    if args.path:
        selected_path = tuple(args.path)
    elif default_run:
        selected_path = DEFAULT_PATH_CHAINS

    verification_names = []
    if not default_run:
        requested = configure_chain_names + list(selected_path or ())
        verification_names = list(dict.fromkeys(requested))

    run_stage(
        "verificar containers e RPCs",
        "verify_yui_infrastructure.py",
        *verification_names,
    )

    if default_run or args.config:
        configure_chains(configure_chain_names)

    configured_path = None
    if selected_path:
        configured_path = configure_path(*selected_path)

    if configured_path:
        print(
            "Configuração concluída. O serviço não foi iniciado.\n"
            "Inicie manualmente com: docker exec yui-relayer "
            f"yrly service start {configured_path}",
            flush=True,
        )
    else:
        print("Configuração da chain concluída.", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nConfiguração interrompida pelo usuário.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f"Falha na configuração do YUI: {error}", file=sys.stderr)
        raise SystemExit(1)
