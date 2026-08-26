import argparse
from pathlib import Path

from .config import load_blockchain_config, load_project_config, select_chains
from .errors import XrplError
from .funding import fund_relayers
from .health import wait_for_chains
from .lifecycle import (
    build,
    ensure_network,
    inspect_service,
    logs,
    status,
    up,
    verify_docker,
)
from .output import stage
from .reconcile import plan_chain, verify_chain
from .render_compose import render_compose


def _load_project(args: argparse.Namespace, root_dir: Path):
    config = load_project_config(
        root_dir,
        config_dir=args.config_dir,
        env_file=args.env_file,
    )
    chains = select_chains(config, getattr(args, "chains", None))
    return config, chains


def _load_blockchain(args: argparse.Namespace, root_dir: Path):
    config = load_blockchain_config(root_dir, config_dir=args.config_dir)
    chains = select_chains(config, getattr(args, "chains", None))
    return config, chains


def _print_selection(chains) -> None:
    print("Chains selecionadas: " + ", ".join(chain.name for chain in chains))


def command_validate(args: argparse.Namespace, root_dir: Path) -> None:
    with stage("validar configuracoes XRPL"):
        _, chains = _load_project(args, root_dir)
        _print_selection(chains)


def command_render(args: argparse.Namespace, root_dir: Path) -> None:
    with stage("validar configuracoes XRPL"):
        config = load_project_config(
            root_dir,
            config_dir=args.config_dir,
            env_file=args.env_file,
        )
        print("Chains no Compose: " + ", ".join(chain.name for chain in config.chains))
    with stage("gerar Compose XRPL"):
        output = render_compose(args.compose_file, config.chains, config.network)
        print(f"Compose: {output}")


def command_init(args: argparse.Namespace, root_dir: Path) -> None:
    with stage("validar configuracoes XRPL"):
        config, chains = _load_project(args, root_dir)
        _print_selection(chains)

    with stage("gerar Compose XRPL"):
        output = render_compose(args.compose_file, config.chains, config.network)
        print(f"Compose: {output}")

    with stage("verificar Docker"):
        verify_docker(root_dir)

    with stage("planejar reconciliacao das chains"):
        plans = tuple(
            plan_chain(
                chain,
                inspect_service(root_dir, args.compose_file, chain.service),
            )
            for chain in chains
        )
        for plan in plans:
            print(f"- {plan.chain.name}: {plan.action} ({plan.reason})")

    actionable_chains = tuple(
        plan.chain for plan in plans if plan.action != "unchanged"
    )

    with stage("criar ou validar rede Docker"):
        created = ensure_network(root_dir, config.network)
        state = "criada" if created else "ja existente e valida"
        print(f"Rede {config.network.name}: {state}")

    if actionable_chains and not args.no_build:
        with stage("construir imagem XRPL"):
            build(
                root_dir,
                args.compose_file,
                tuple(chain.service for chain in actionable_chains),
            )

    if actionable_chains:
        with stage("iniciar containers XRPL"):
            up(
                root_dir,
                args.compose_file,
                tuple(chain.service for chain in actionable_chains),
            )
    else:
        print("Nenhuma alteracao de container necessaria.")

    with stage("verificar reconciliacao das chains"):
        for chain in chains:
            verify_chain(
                chain,
                inspect_service(root_dir, args.compose_file, chain.service),
            )

    results = ()
    if not args.no_wait:
        with stage("aguardar RPC, REST e EVM"):
            results = wait_for_chains(chains, timeout=args.timeout)

    print("XRPL inicializada.")
    for chain in chains:
        evm = next(
            (result.evm_chain_id for result in results if result.chain == chain),
            "nao verificado",
        )
        print(
            f"- {chain.name}: RPC={chain.ports.rpc} REST={chain.ports.rest} "
            f"EVM={chain.ports.evm_rpc} EVM-chain-id={evm}"
        )


def command_status(args: argparse.Namespace, root_dir: Path) -> None:
    with stage("verificar Docker"):
        verify_docker(root_dir)
    status(root_dir, args.compose_file)


def command_fund_relayers(args: argparse.Namespace, root_dir: Path) -> None:
    with stage("validar configuracoes e contas XRPL"):
        config, chains = _load_blockchain(args, root_dir)
        _print_selection(chains)

    with stage("financiar contas dos relayers"):
        fund_relayers(config, chains, args.amount)


def command_logs(args: argparse.Namespace, root_dir: Path) -> None:
    config = load_blockchain_config(
        root_dir,
        config_dir=args.config_dir,
    )
    chain = select_chains(config, [args.chain])[0]
    if args.tail < 0:
        raise XrplError("--tail deve ser maior ou igual a zero")
    logs(
        root_dir,
        args.compose_file,
        chain.service,
        follow=args.follow,
        tail=args.tail,
    )


COMMANDS = {
    "validate": command_validate,
    "render": command_render,
    "init": command_init,
    "fund-relayers": command_fund_relayers,
    "status": command_status,
    "logs": command_logs,
}
