from pathlib import Path
import json
import os

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
CHAINS_FILE = ROOT_DIR / "chains.json"
ENV_FILE = ROOT_DIR / ".env"
OUTPUT_FILE = ROOT_DIR / "docker-compose.yaml"


def load_chains():
    data = json.loads(CHAINS_FILE.read_text(encoding="utf-8"))
    return data["chains"]


def volume_name(chain):
    return chain.get("volume", f"{chain['service']}-data")


def render_chain_service(chain, include_build=False):
    build_block = "    build: *xrplevm-build\n" if include_build else ""
    
    return f"""  {chain["service"]}:
    image: xrplevm-local:dev 
{build_block}    container_name: {chain["service"]}
    command: ["/usr/local/bin/start-persistent.sh"]
    environment:
      CHAIN_ID: {json.dumps(str(chain["chain_id"]))}
      MONIKER: {json.dumps(str(chain["name"]))}
      CHAIN_NAME: {json.dumps(str(chain["name"]))}
    ports:
      - "{chain["rpc_port"]}:26657"
      - "{chain["rest_port"]}:1317"
      - "{chain["grpc_port"]}:9090"
      - "{chain["evm_rpc_port"]}:8545"
      - "{chain["evm_ws_port"]}:8546"
    networks:
      xrplevm_net:
        ipv4_address: {chain["ip"]}
    volumes:
      - {volume_name(chain)}:/app/.exrpd
"""


def render_compose():
    load_dotenv(ENV_FILE)

    chains = load_chains()

    services = "\n".join(
        render_chain_service(chain, include_build=(index == 0))
        for index, chain in enumerate(chains)
    )
    
    depends_on = "\n".join(
        f"      - {chain['service']}" for chain in chains
    )

    volumes = "\n".join(
        f"  {volume_name(chain)}:" for chain in chains
    )

    content = f"""x-xrplevm-build: &xrplevm-build
  context: .
  dockerfile: Dockerfile

services:
{services}
  yui-relayer:
    image: yui-relayer-local:dev
    build:
      context: ./yui-relayer
      dockerfile: Dockerfile
    container_name: yui-relayer
    entrypoint: ["sleep"]
    command: ["infinity"]
    volumes:
      - ./relayer_config/yui:/root/.yui-relayer
    depends_on:
{depends_on}
    networks:
      xrplevm_net:
        ipv4_address: {os.environ["YUI_RELAYER_IP"]}

networks:
  xrplevm_net:
    name: {os.environ["DOCKER_NETWORK_NAME"]}
    driver: {os.environ["DOCKER_NETWORK_DRIVER"]}
    ipam:
      config:
        - subnet: {os.environ["DOCKER_SUBNET"]}
          gateway: {os.environ["DOCKER_GATEWAY"]}

volumes:
{volumes}
"""

    OUTPUT_FILE.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    render_compose()
    print(f"Compose: {OUTPUT_FILE}")
