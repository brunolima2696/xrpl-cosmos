from dataclasses import dataclass
from typing import Any

from .errors import ReconcileError
from .fingerprint import (
    CONFIG_HASH_LABEL,
    IDENTITY_HASH_LABEL,
    chain_config_hash,
    chain_identity_hash,
)
from .models import Chain


@dataclass(frozen=True)
class ReconcilePlan:
    chain: Chain
    action: str
    reason: str


def _environment(inspection: dict[str, Any]) -> dict[str, str]:
    entries = inspection.get("Config", {}).get("Env", []) or []
    environment: dict[str, str] = {}
    for entry in entries:
        if isinstance(entry, str) and "=" in entry:
            key, value = entry.split("=", 1)
            environment[key] = value
    return environment


def _data_volume(inspection: dict[str, Any]) -> str | None:
    for mount in inspection.get("Mounts", []) or []:
        if mount.get("Destination") == "/app/.exrpd":
            return mount.get("Name") or mount.get("Source")
    return None


def _volume_matches(actual: str, expected: str) -> bool:
    return actual == expected or actual.endswith(f"_{expected}")


def _validate_identity(chain: Chain, inspection: dict[str, Any]) -> None:
    environment = _environment(inspection)
    labels = inspection.get("Config", {}).get("Labels", {}) or {}
    actual_chain_id = environment.get("CHAIN_ID")
    actual_name = environment.get("MONIKER") or environment.get("CHAIN_NAME")
    actual_volume = _data_volume(inspection)
    actual_service = labels.get("com.docker.compose.service")

    unknown = []
    if not actual_chain_id:
        unknown.append("chain_id")
    if not actual_name:
        unknown.append("nome/moniker")
    if not actual_volume:
        unknown.append("volume")
    if unknown:
        raise ReconcileError(
            f"{chain.name}: nao foi possivel verificar a identidade atual: "
            + ", ".join(unknown)
        )

    differences = []
    if actual_chain_id != chain.chain_id:
        differences.append(f"chain_id atual={actual_chain_id!r}, declarado={chain.chain_id!r}")
    if actual_name != chain.name:
        differences.append(f"nome atual={actual_name!r}, declarado={chain.name!r}")
    if not _volume_matches(actual_volume, chain.volume):
        differences.append(f"volume atual={actual_volume!r}, declarado={chain.volume!r}")
    if actual_service and actual_service != chain.service:
        differences.append(
            f"service atual={actual_service!r}, declarado={chain.service!r}"
        )
    identity_hash = labels.get(IDENTITY_HASH_LABEL)
    if identity_hash and identity_hash != chain_identity_hash(chain):
        differences.append("fingerprint de identidade diferente")
    if differences:
        raise ReconcileError(
            f"{chain.name}: alteracao de identidade nao pode reutilizar o estado "
            f"existente ({'; '.join(differences)})"
        )


def plan_chain(
    chain: Chain,
    inspection: dict[str, Any] | None,
) -> ReconcilePlan:
    if inspection is None:
        return ReconcilePlan(chain, "create", "container ainda nao existe")

    _validate_identity(chain, inspection)
    labels = inspection.get("Config", {}).get("Labels", {}) or {}
    current_hash = labels.get(CONFIG_HASH_LABEL)
    desired_hash = chain_config_hash(chain)
    running = bool(inspection.get("State", {}).get("Running"))

    if current_hash != desired_hash:
        return ReconcilePlan(
            chain,
            "recreate",
            "configuracao declarada foi alterada"
            if current_hash
            else "container anterior nao possui metadados de reconciliacao",
        )
    if not running:
        return ReconcilePlan(chain, "start", "container existente esta parado")
    return ReconcilePlan(chain, "unchanged", "container ja corresponde ao declarado")


def verify_chain(chain: Chain, inspection: dict[str, Any] | None) -> None:
    if inspection is None:
        raise ReconcileError(f"{chain.name}: container nao foi criado")
    _validate_identity(chain, inspection)
    if not inspection.get("State", {}).get("Running"):
        raise ReconcileError(f"{chain.name}: container nao esta em execucao")
    labels = inspection.get("Config", {}).get("Labels", {}) or {}
    if labels.get(CONFIG_HASH_LABEL) != chain_config_hash(chain):
        raise ReconcileError(
            f"{chain.name}: container iniciado nao corresponde a configuracao declarada"
        )
