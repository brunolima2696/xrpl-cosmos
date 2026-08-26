from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Ports:
    rpc: int
    rest: int
    grpc: int
    evm_rpc: int
    evm_ws: int

    def host_ports(self) -> tuple[int, ...]:
        return (self.rpc, self.rest, self.grpc, self.evm_rpc, self.evm_ws)


@dataclass(frozen=True)
class Chain:
    name: str
    profile: str
    chain_id: str
    service: str
    ip: str
    ports: Ports
    volume: str


@dataclass(frozen=True)
class DockerNetwork:
    name: str
    driver: str
    subnet: str
    gateway: str


@dataclass(frozen=True)
class BlockchainConfig:
    root_dir: Path
    config_dir: Path
    profile: dict[str, Any]
    chains: tuple[Chain, ...]


@dataclass(frozen=True)
class ProjectConfig(BlockchainConfig):
    network: DockerNetwork
