import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from .errors import HealthError
from .models import Chain


@dataclass(frozen=True)
class HealthResult:
    chain: Chain
    evm_chain_id: str


def _json_request(
    url: str,
    *,
    payload: dict[str, object] | None = None,
    timeout: float = 3.0,
) -> dict[str, object]:
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _check_chain(chain: Chain) -> HealthResult:
    rpc = _json_request(f"http://127.0.0.1:{chain.ports.rpc}/status")
    actual_chain_id = (
        rpc.get("result", {})
        .get("node_info", {})
        .get("network")
    )
    if actual_chain_id != chain.chain_id:
        raise HealthError(
            f"{chain.name}: RPC retornou chain_id {actual_chain_id!r}; "
            f"esperado {chain.chain_id!r}"
        )

    _json_request(
        f"http://127.0.0.1:{chain.ports.rest}/cosmos/base/tendermint/v1beta1/node_info"
    )
    evm = _json_request(
        f"http://127.0.0.1:{chain.ports.evm_rpc}",
        payload={
            "jsonrpc": "2.0",
            "method": "eth_chainId",
            "params": [],
            "id": 1,
        },
    )
    evm_chain_id = evm.get("result")
    if not isinstance(evm_chain_id, str) or not evm_chain_id:
        raise HealthError(f"{chain.name}: resposta EVM invalida: {evm}")
    return HealthResult(chain=chain, evm_chain_id=evm_chain_id)


def _wait_for_chain(chain: Chain, timeout: float, interval: float) -> HealthResult:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return _check_chain(chain)
        except (
            HealthError,
            OSError,
            TimeoutError,
            ValueError,
            json.JSONDecodeError,
            urllib.error.URLError,
        ) as exc:
            last_error = exc
            time.sleep(interval)
    raise HealthError(
        f"{chain.name} nao ficou pronta em {timeout:.0f}s: {last_error}"
    )


def wait_for_chains(
    chains: tuple[Chain, ...],
    *,
    timeout: float = 180.0,
    interval: float = 2.0,
) -> tuple[HealthResult, ...]:
    results: dict[str, HealthResult] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=len(chains)) as executor:
        futures = {
            executor.submit(_wait_for_chain, chain, timeout, interval): chain
            for chain in chains
        }
        for future in as_completed(futures):
            chain = futures[future]
            try:
                results[chain.name] = future.result()
            except Exception as exc:
                failures.append(str(exc))
    if failures:
        raise HealthError("; ".join(failures))
    return tuple(results[chain.name] for chain in chains)
