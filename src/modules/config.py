import ipaddress
import json
import re
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .models import BlockchainConfig, Chain, DockerNetwork, Ports, ProjectConfig


REQUIRED_NETWORK_VALUES = (
    "DOCKER_NETWORK_DRIVER",
    "DOCKER_NETWORK_NAME",
    "DOCKER_SUBNET",
    "DOCKER_GATEWAY",
)
REQUIRED_PORTS = ("rpc", "rest", "grpc", "evm_rpc", "evm_ws")
SERVICE_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Arquivo de configuracao nao encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(
            f"JSON invalido em {path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        ) from exc


def _read_env(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError as exc:
        raise ConfigError(f"Arquivo de ambiente nao encontrado: {path}") from exc

    values: dict[str, str] = {}
    for line_number, original in enumerate(lines, start=1):
        line = original.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            raise ConfigError(f"Linha invalida em {path}:{line_number}")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    return values


def _required_string(data: dict[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{context}: campo obrigatorio ausente ou invalido: {key}")
    return value.strip()


def _parse_port(value: Any, key: str, context: str) -> int:
    if isinstance(value, bool):
        raise ConfigError(f"{context}: porta invalida em ports.{key}: {value}")
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{context}: porta invalida em ports.{key}: {value}") from exc
    if not 1 <= port <= 65535:
        raise ConfigError(f"{context}: porta fora do intervalo em ports.{key}: {port}")
    return port


def _load_network(env_file: Path) -> DockerNetwork:
    values = _read_env(env_file)
    missing = [key for key in REQUIRED_NETWORK_VALUES if not values.get(key)]
    if missing:
        raise ConfigError(
            f"{env_file}: variaveis Docker ausentes: {', '.join(missing)}"
        )

    subnet_text = values["DOCKER_SUBNET"]
    gateway_text = values["DOCKER_GATEWAY"]
    try:
        subnet = ipaddress.ip_network(subnet_text, strict=False)
        gateway = ipaddress.ip_address(gateway_text)
    except ValueError as exc:
        raise ConfigError(f"Rede Docker invalida em {env_file}: {exc}") from exc
    if gateway not in subnet:
        raise ConfigError(f"Gateway {gateway} nao pertence a subnet {subnet}")

    return DockerNetwork(
        name=values["DOCKER_NETWORK_NAME"],
        driver=values["DOCKER_NETWORK_DRIVER"],
        subnet=str(subnet),
        gateway=str(gateway),
    )


def _load_chains(chains_file: Path, profile_name: str) -> tuple[Chain, ...]:
    document = _read_json(chains_file)
    raw_chains = document.get("chains") if isinstance(document, dict) else None
    if not isinstance(raw_chains, list) or not raw_chains:
        raise ConfigError(f"{chains_file}: chains deve ser uma lista nao vazia")

    chains: list[Chain] = []
    for index, raw in enumerate(raw_chains):
        context = f"{chains_file}: chains[{index}]"
        if not isinstance(raw, dict):
            raise ConfigError(f"{context}: deve ser um objeto")

        name = _required_string(raw, "name", context)
        chain_profile = _required_string(raw, "profile", context)
        if chain_profile != profile_name:
            raise ConfigError(
                f"{context}: profile {chain_profile!r} nao corresponde a {profile_name!r}"
            )

        ports_data = raw.get("ports")
        if not isinstance(ports_data, dict):
            raise ConfigError(f"{context}: campo ports deve ser um objeto")
        missing_ports = [key for key in REQUIRED_PORTS if key not in ports_data]
        if missing_ports:
            raise ConfigError(
                f"{context}: portas ausentes: {', '.join(missing_ports)}"
            )

        service = _required_string(raw, "service", context)
        if not SERVICE_PATTERN.fullmatch(service):
            raise ConfigError(f"{context}: nome de service invalido: {service}")

        chains.append(
            Chain(
                name=name,
                profile=chain_profile,
                chain_id=_required_string(raw, "chain_id", context),
                service=service,
                ip=_required_string(raw, "ip", context),
                ports=Ports(
                    **{
                        key: _parse_port(ports_data[key], key, context)
                        for key in REQUIRED_PORTS
                    }
                ),
                volume=str(raw.get("volume") or f"{service}-data"),
            )
        )
    return tuple(chains)


def _validate_uniqueness(chains: tuple[Chain, ...]) -> None:
    fields = {
        "name": [chain.name for chain in chains],
        "service": [chain.service for chain in chains],
        "chain_id": [chain.chain_id for chain in chains],
        "ip": [chain.ip for chain in chains],
        "volume": [chain.volume for chain in chains],
    }
    for field, values in fields.items():
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ConfigError(
                f"Valores duplicados em chains.{field}: {', '.join(duplicates)}"
            )

    ports: dict[int, str] = {}
    for chain in chains:
        for port in chain.ports.host_ports():
            owner = ports.get(port)
            if owner:
                raise ConfigError(
                    f"Porta host {port} duplicada entre {owner} e {chain.name}"
                )
            ports[port] = chain.name


def _validate_chain_ips(chains: tuple[Chain, ...], network: DockerNetwork) -> None:
    subnet = ipaddress.ip_network(network.subnet, strict=False)
    gateway = ipaddress.ip_address(network.gateway)
    for chain in chains:
        try:
            address = ipaddress.ip_address(chain.ip)
        except ValueError as exc:
            raise ConfigError(f"{chain.name}: IP invalido: {chain.ip}") from exc
        if address not in subnet:
            raise ConfigError(
                f"{chain.name}: IP {address} nao pertence a subnet {subnet}"
            )
        if address == gateway:
            raise ConfigError(f"{chain.name}: IP nao pode ser igual ao gateway")


def load_blockchain_config(
    root_dir: Path,
    config_dir: Path | None = None,
) -> BlockchainConfig:
    root_dir = root_dir.resolve()
    config_dir = (config_dir or root_dir / "config").resolve()

    profile_file = config_dir / "profile.json"
    profile = _read_json(profile_file)
    if not isinstance(profile, dict):
        raise ConfigError(f"{profile_file}: deve conter um objeto JSON")
    profile_name = _required_string(profile, "name", str(profile_file))

    chains = _load_chains(config_dir / "chains.json", profile_name)
    _validate_uniqueness(chains)

    return BlockchainConfig(
        root_dir=root_dir,
        config_dir=config_dir,
        profile=profile,
        chains=chains,
    )


def load_project_config(
    root_dir: Path,
    config_dir: Path | None = None,
    env_file: Path | None = None,
) -> ProjectConfig:
    blockchain = load_blockchain_config(root_dir, config_dir)
    env_file = (env_file or blockchain.root_dir / ".env").resolve()
    network = _load_network(env_file)
    _validate_chain_ips(blockchain.chains, network)

    return ProjectConfig(
        root_dir=blockchain.root_dir,
        config_dir=blockchain.config_dir,
        profile=blockchain.profile,
        chains=blockchain.chains,
        network=network,
    )


def select_chains(
    config: BlockchainConfig,
    requested: list[str] | None,
) -> tuple[Chain, ...]:
    if not requested:
        return config.chains

    aliases: dict[str, Chain] = {}
    for chain in config.chains:
        for alias in (chain.name, chain.service, chain.chain_id):
            aliases[alias] = chain

    selected: list[Chain] = []
    unknown: list[str] = []
    for value in requested:
        chain = aliases.get(value)
        if chain is None:
            unknown.append(value)
        elif chain not in selected:
            selected.append(chain)
    if unknown:
        raise ConfigError(f"Chains nao encontradas: {', '.join(unknown)}")
    return tuple(selected)
