import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .commands import COMMANDS
from .errors import XrplError


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _positive_xrp(value: str) -> Decimal:
    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"quantidade de XRP invalida: {value}") from exc
    if not amount.is_finite() or amount <= 0:
        raise argparse.ArgumentTypeError("a quantidade de XRP deve ser maior que zero")
    return amount


DISPLAY_ROOT = "xrpl-cosmos"


def _add_config_dir(parser: argparse.ArgumentParser, root_dir: Path) -> None:
    parser.add_argument(
        "--config-dir",
        type=_path,
        default=root_dir / "config",
        help=f"diretorio declarativo (padrao: {DISPLAY_ROOT}/config)",
    )


def _add_env_file(parser: argparse.ArgumentParser, root_dir: Path) -> None:
    parser.add_argument(
        "--env-file",
        type=_path,
        default=root_dir / ".env",
        help=f"arquivo com a rede Docker (padrao: {DISPLAY_ROOT}/.env)",
    )


def _add_compose_file(parser: argparse.ArgumentParser, root_dir: Path) -> None:
    parser.add_argument(
        "--compose-file",
        type=_path,
        default=root_dir / "docker-compose.yaml",
        help=f"Compose (padrao: {DISPLAY_ROOT}/docker-compose.yaml)",
    )


def _add_chain_selector(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--chain",
        action="append",
        dest="chains",
        metavar="CHAIN",
        help="chain alvo; pode ser repetido; usa todas por padrao",
    )


def build_parser(root_dir: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inicializa e gerencia as XRPL EVM Sidechains locais."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser(
        "validate", help="valida configuracoes sem alterar o ambiente"
    )
    _add_config_dir(validate_parser, root_dir)
    _add_env_file(validate_parser, root_dir)
    _add_chain_selector(validate_parser)

    render_parser = subparsers.add_parser(
        "render", help="gera o Compose das chains XRPL"
    )
    _add_config_dir(render_parser, root_dir)
    _add_env_file(render_parser, root_dir)
    _add_compose_file(render_parser, root_dir)

    init_parser = subparsers.add_parser(
        "init", help="inicializa ou reconcilia as chains XRPL"
    )
    _add_config_dir(init_parser, root_dir)
    _add_env_file(init_parser, root_dir)
    _add_compose_file(init_parser, root_dir)
    _add_chain_selector(init_parser)
    init_parser.add_argument(
        "--no-build", action="store_true", help="nao executa o build"
    )
    init_parser.add_argument(
        "--no-wait", action="store_true", help="nao aguarda os RPCs"
    )
    init_parser.add_argument(
        "--timeout",
        type=float,
        default=180.0,
        help="tempo maximo por chain para healthcheck, em segundos",
    )

    fund_parser = subparsers.add_parser(
        "fund-relayers",
        help="envia XRP da Alice para as contas dos relayers",
    )
    _add_config_dir(fund_parser, root_dir)
    _add_chain_selector(fund_parser)
    fund_parser.add_argument(
        "--amount",
        type=_positive_xrp,
        default=Decimal("1000"),
        metavar="XRP",
        help="XRP enviado para cada relayer (padrao: 1000)",
    )

    status_parser = subparsers.add_parser(
        "status", help="exibe o estado dos containers XRPL"
    )
    _add_compose_file(status_parser, root_dir)

    logs_parser = subparsers.add_parser(
        "logs", help="exibe logs de uma chain XRPL"
    )
    _add_config_dir(logs_parser, root_dir)
    _add_compose_file(logs_parser, root_dir)
    logs_parser.add_argument("chain", help="name, service ou chain_id")
    logs_parser.add_argument("--follow", action="store_true")
    logs_parser.add_argument("--tail", type=int, default=100)
    return parser


def run(root_dir: Path, argv: list[str] | None = None) -> int:
    root_dir = root_dir.resolve()
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(root_dir)
    if not argv:
        parser.print_help()
        return 0
    args = parser.parse_args(argv)
    try:
        COMMANDS[args.command](args, root_dir)
    except (XrplError, OSError) as exc:
        print(f"Falha: {exc}", file=sys.stderr)
        return 1
    return 0
