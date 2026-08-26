import hashlib
import json
from dataclasses import asdict

from .models import Chain


CONFIG_HASH_LABEL = "io.xrpl-cosmos.chain-config-hash"
IDENTITY_HASH_LABEL = "io.xrpl-cosmos.chain-identity-hash"


def _hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def chain_config_hash(chain: Chain) -> str:
    return _hash(asdict(chain))


def chain_identity_hash(chain: Chain) -> str:
    return _hash(
        {
            "chain_id": chain.chain_id,
            "name": chain.name,
            "service": chain.service,
            "volume": chain.volume,
        }
    )
