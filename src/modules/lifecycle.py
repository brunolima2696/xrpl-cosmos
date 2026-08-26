import json
import shutil
import subprocess
from pathlib import Path
from typing import Sequence

from .errors import DockerError
from .models import DockerNetwork


def _run(
    args: Sequence[str],
    *,
    cwd: Path,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(args),
            cwd=cwd,
            check=check,
            text=True,
            capture_output=capture,
        )
    except FileNotFoundError as exc:
        raise DockerError(f"Comando nao encontrado: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or "").strip()
        suffix = f": {details}" if details else ""
        raise DockerError(
            f"Comando falhou com codigo {exc.returncode}: {' '.join(args)}{suffix}"
        ) from exc


def verify_docker(root_dir: Path) -> None:
    if shutil.which("docker") is None:
        raise DockerError("docker nao foi encontrado no PATH")
    _run(("docker", "compose", "version"), cwd=root_dir, capture=True)
    _run(("docker", "info", "--format", "{{.ServerVersion}}"), cwd=root_dir, capture=True)


def ensure_network(root_dir: Path, network: DockerNetwork) -> bool:
    result = _run(
        ("docker", "network", "inspect", network.name),
        cwd=root_dir,
        capture=True,
        check=False,
    )
    if result.returncode != 0:
        _run(
            (
                "docker",
                "network",
                "create",
                "--driver",
                network.driver,
                "--subnet",
                network.subnet,
                "--gateway",
                network.gateway,
                network.name,
            ),
            cwd=root_dir,
        )
        return True

    try:
        current = json.loads(result.stdout)[0]
    except (json.JSONDecodeError, IndexError, TypeError) as exc:
        raise DockerError(f"Resposta invalida ao inspecionar a rede {network.name}") from exc

    actual_driver = current.get("Driver")
    ipam_configs = current.get("IPAM", {}).get("Config", [])
    compatible_ipam = any(
        item.get("Subnet") == network.subnet
        and item.get("Gateway") == network.gateway
        for item in ipam_configs
    )
    if actual_driver != network.driver or not compatible_ipam:
        raise DockerError(
            f"Rede {network.name} existe com configuracao diferente: "
            f"driver={actual_driver}, ipam={ipam_configs}"
        )
    return False


def _compose_command(compose_file: Path, *args: str) -> tuple[str, ...]:
    return ("docker", "compose", "-f", str(compose_file), *args)


def build(root_dir: Path, compose_file: Path, services: Sequence[str]) -> None:
    _run(_compose_command(compose_file, "build", *services), cwd=root_dir)


def up(root_dir: Path, compose_file: Path, services: Sequence[str]) -> None:
    _run(
        _compose_command(compose_file, "up", "-d", "--no-build", *services),
        cwd=root_dir,
    )


def inspect_service(
    root_dir: Path,
    compose_file: Path,
    service: str,
) -> dict | None:
    result = _run(
        _compose_command(compose_file, "ps", "--all", "--quiet", service),
        cwd=root_dir,
        capture=True,
    )
    container_ids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not container_ids:
        return None
    if len(container_ids) > 1:
        raise DockerError(
            f"Mais de um container encontrado para o servico {service}: "
            + ", ".join(container_ids)
        )
    inspection = _run(
        ("docker", "inspect", container_ids[0]),
        cwd=root_dir,
        capture=True,
    )
    try:
        document = json.loads(inspection.stdout)
        current = document[0]
    except (json.JSONDecodeError, IndexError, TypeError) as exc:
        raise DockerError(f"Resposta invalida ao inspecionar {service}") from exc
    if not isinstance(current, dict):
        raise DockerError(f"Resposta invalida ao inspecionar {service}")
    return current


def status(root_dir: Path, compose_file: Path) -> None:
    if not compose_file.exists():
        raise DockerError(f"Compose XRPL nao encontrado: {compose_file}")
    _run(_compose_command(compose_file, "ps"), cwd=root_dir)


def logs(
    root_dir: Path,
    compose_file: Path,
    service: str,
    *,
    follow: bool,
    tail: int,
) -> None:
    if not compose_file.exists():
        raise DockerError(f"Compose XRPL nao encontrado: {compose_file}")
    args = ["logs", "--tail", str(tail)]
    if follow:
        args.append("--follow")
    args.append(service)
    _run(_compose_command(compose_file, *args), cwd=root_dir)
