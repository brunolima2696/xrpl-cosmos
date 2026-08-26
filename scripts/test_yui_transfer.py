import argparse
import hashlib
import json
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests


ROOT_DIR = Path(__file__).resolve().parents[1]
UTILS_DIR = ROOT_DIR / "scripts" / "utils"
sys.path.insert(0, str(UTILS_DIR))

from yui_common import (  # noqa: E402
    chain_transfer_config,
    path_name,
    run_yui,
    select_chains,
    yui_config,
)


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Envia uma transferência pelo YUI e confirma recebimento e "
            "acknowledgment. O serviço do path deve estar ativo."
        )
    )
    parser.add_argument("source", help="name da chain de origem")
    parser.add_argument("destination", help="name da chain de destino")
    parser.add_argument(
        "--amount",
        default="1",
        help="quantidade na unidade principal do token (padrão: 1)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=180,
        help="tempo máximo de confirmação em segundos (padrão: 180)",
    )
    return parser.parse_args()


def to_base_units(amount_text, decimals):
    try:
        amount = Decimal(amount_text)
    except InvalidOperation as error:
        raise ValueError(f"Quantidade inválida: {amount_text}") from error
    if amount <= 0:
        raise ValueError("A quantidade deve ser maior que zero")

    scaled = amount * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise ValueError(
            f"Quantidade possui mais de {decimals} casas decimais"
        )
    return int(scaled)


def yui_key_address(chain):
    result = run_yui(
        "tendermint",
        "keys",
        "show",
        chain["chain_id"],
        chain["key_name"],
        capture=True,
    )
    return result.stdout.strip()


def bank_balance(chain, address, denom):
    url = (
        f"http://127.0.0.1:{chain['rest_port']}"
        f"/cosmos/bank/v1beta1/balances/{address}/by_denom"
    )
    response = requests.get(url, params={"denom": denom}, timeout=10)
    response.raise_for_status()
    return int((response.json().get("balance") or {}).get("amount", "0"))


def extract_tx_hash(output, source_chain_id):
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            event.get("msg") == "success-tx"
            and event.get("chain-id") == source_chain_id
            and event.get("hash")
        ):
            return event["hash"]

    match = re.search(r'"hash":"([0-9A-Fa-f]+)"', output)
    if match:
        return match.group(1)
    raise RuntimeError("Não foi possível identificar o hash da transferência")


def packet_sequence(chain, tx_hash, deadline):
    url = (
        f"http://127.0.0.1:{chain['rest_port']}"
        f"/cosmos/tx/v1beta1/txs/{tx_hash}"
    )
    while time.monotonic() < deadline:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            events = response.json().get("tx_response", {}).get("events", [])
            for event in events:
                if event.get("type") != "send_packet":
                    continue
                for attribute in event.get("attributes", []):
                    if attribute.get("key") == "packet_sequence":
                        return int(attribute["value"])
        elif response.status_code != 404:
            response.raise_for_status()
        time.sleep(2)
    raise TimeoutError("A sequência do pacote não apareceu no índice de transações")


def packet_commitment_exists(chain, endpoint, sequence):
    url = (
        f"http://127.0.0.1:{chain['rest_port']}"
        "/ibc/core/channel/v1/channels/"
        f"{endpoint['channel-id']}/ports/{endpoint['port-id']}"
        "/packet_commitments"
    )
    response = requests.get(
        url,
        params={"pagination.limit": "1000"},
        timeout=10,
    )
    response.raise_for_status()
    commitments = response.json().get("commitments", [])
    return any(int(item["sequence"]) == sequence for item in commitments)


def wait_for_balance(chain, address, denom, expected_balance, deadline):
    while time.monotonic() < deadline:
        current = bank_balance(chain, address, denom)
        if current >= expected_balance:
            return current
        time.sleep(2)
    raise TimeoutError(
        f"Voucher {denom} não foi recebido antes do timeout"
    )


def wait_for_ack(chain, endpoint, sequence, deadline):
    while time.monotonic() < deadline:
        if not packet_commitment_exists(chain, endpoint, sequence):
            return
        time.sleep(2)
    raise TimeoutError(
        f"Acknowledgment do pacote {sequence} não retornou antes do timeout"
    )


def main():
    args = parse_args()
    if args.source == args.destination:
        raise ValueError("As chains de origem e destino devem ser diferentes")

    source, destination = select_chains([args.source, args.destination])
    name = path_name(args.source, args.destination)
    path = yui_config().get("paths", {}).get(name)
    if not path:
        raise RuntimeError(f"Path não configurado no YUI: {name}")

    src_endpoint = path["src"]
    dst_endpoint = path["dst"]
    if src_endpoint.get("chain-id") != source["chain_id"]:
        raise RuntimeError(
            f"{source['name']} não é a origem configurada no path {name}"
        )
    if dst_endpoint.get("chain-id") != destination["chain_id"]:
        raise RuntimeError(
            f"{destination['name']} não é o destino configurado no path {name}"
        )
    for endpoint_name, endpoint in (("src", src_endpoint), ("dst", dst_endpoint)):
        if not endpoint.get("channel-id") or not endpoint.get("port-id"):
            raise RuntimeError(f"Endpoint {endpoint_name} sem channel ou port")

    transfer = chain_transfer_config(source)
    denom = transfer["denom"]
    amount = to_base_units(args.amount, int(transfer["decimals"]))
    receiver = yui_key_address(destination)

    trace = f"{dst_endpoint['port-id']}/{dst_endpoint['channel-id']}/{denom}"
    voucher_denom = "ibc/" + hashlib.sha256(trace.encode()).hexdigest().upper()
    initial_balance = bank_balance(destination, receiver, voucher_denom)

    print(
        f"Enviando {args.amount} unidade(s) principal(is) "
        f"({amount}{denom}) de {source['name']} para "
        f"{destination['name']}...",
        flush=True,
    )
    result = run_yui(
        "tx",
        "transfer",
        name,
        source["chain_id"],
        destination["chain_id"],
        f"{amount}{denom}",
        receiver,
        "--timeout-time-offset=5m",
        capture=True,
        check=False,
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if output:
        print(output.rstrip())
    if result.returncode != 0:
        raise RuntimeError("Falha ao enviar a transferência na chain de origem")

    tx_hash = extract_tx_hash(output, source["chain_id"])
    deadline = time.monotonic() + args.timeout
    sequence = packet_sequence(source, tx_hash, deadline)
    final_balance = wait_for_balance(
        destination,
        receiver,
        voucher_denom,
        initial_balance + amount,
        deadline,
    )
    wait_for_ack(source, src_endpoint, sequence, deadline)

    print("Transferência IBC confirmada.")
    print(f"Tx origem: {tx_hash}")
    print(f"Pacote: {sequence}")
    print(f"Recebedor: {receiver}")
    print(f"Voucher: {voucher_denom}")
    print(f"Saldo anterior: {initial_balance}")
    print(f"Saldo atual: {final_balance}")
    print("Acknowledgment confirmado na origem.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nTeste interrompido pelo usuário.", file=sys.stderr)
        raise SystemExit(130)
    except Exception as error:
        print(f"Falha no teste IBC: {error}", file=sys.stderr)
        raise SystemExit(1)
