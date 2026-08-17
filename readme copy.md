# Inicialização das chains A, B e do Relayer Hermes:
```
docker compose up -d --build
```

## Validação do funcionamento das chains A e B:

Para verificar o funcionamento das chains,  `docker logs -f xrplevm-a` e, em um segundo terminal `docker logs -f xrplevm-b`.

### Verificação dos endpoints:
#### Chain A
##### RPC Cosmos
```
curl http://localhost:26657/status
```
##### RPC EVM
```
curl -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  http://localhost:8545
```
#### Chain B
##### RPC Cosmos
```
curl http://localhost:36657/status
```
##### RPC EVM
```
curl -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  http://localhost:9545
```

## Validação do funcionamento do Relayer:

Health Check: `docker exec -it hermes hermes health-check`.

Para validar o arquivo de configuração: `docker exec -it hermes hermes config validate`.

### Importação dos mnemonics para o Hermes:

```
python scripts/import_relayer_keys.py
```

e, para validar a importação: `docker exec -it hermes hermes keys list --chain {CHAIN_ID}`. Por exemplo: `docker exec -it hermes hermes keys list --chain xrplevm_1450001-1`


### Adicionando fundos às contas dos relayers:

```
python scripts/fund_relayers.py
```


### Criação do canal IBC transfer entre duas chains:
Para haver comunicação entre duas chains X e Y, um canal IBC deve ser explicitamente aberto. Entre as chains A e B:
```
docker exec -it hermes sh -lc 'hermes create channel \
  --a-chain xrplevm_1450001-1 \
  --b-chain xrplevm_1450002-1 \
  --a-port transfer \
  --b-port transfer \
  --new-client-connection \
  --yes
```
Um segundo canal, entre as chains A e C:
```
docker exec -it hermes hermes create channel \
  --a-chain xrplevm_1450001-1 \
  --b-chain xrplevm_1450003-1 \
  --a-port transfer \
  --b-port transfer \
  --new-client-connection
  --yes
```

#### Para validar ou verificar os canais abertos para uma chain, execute `docker exec -it hermes hermes query channels --chain {CHAIN_ID}`. Para a Chain A, por exmeplo: ` docker exec -it hermes hermes query channels --chain xrplevm_1450001-1`.

A saída mostrará algo como:
```
PortChannelId {
        channel_id: ChannelId(
            "channel-0",
        ),
        port_id: PortId(
            "transfer",
        ),
    },
```
Ou seja, o ` channel-0` será o utilizado 

### Execução do Relayer Hermes
Em um segundo terminal, execute:

```
docker exec -it hermes hermes start
```


### Transferência Cross-Chain:
Executa uma transferência de token (asset transfer) via protocolo IBC usando padrão ICS-20, da Chain A para Chain B.

```
python tests/transfer_cross_chain.py
```

A saída - também salva no arquivo `logfile.jsonl` - será do tipo:

```
{
  "Source Chain": "xrplevm_1449999-1",
  "Source Port": "transfer",
  "Source Channel": "channel-0",
  "Sender Chain A": "ethm1dakgyqjulg29m5fmv992g2y66m9g2mjn6hahwg",
  "Receiver Chain B": "ethm1dakgyqjulg29m5fmv992g2y66m9g2mjn6hahwg",
  "Amount": "1 XRP",
  "Amount axrp": "1000000000000000000",
  "Code": 0,
  "TxHash": "EC7F3BA4B24238357EB657DC2B9A2AC05B7F79F7D354D782DFA07539D4157EC7"
}
```

### Validação na Chain B:

A confirmação da transferência do token para a Chain B pode ser conferida ao executar o script `check_balance_cosmos.py` com os parâmetros `COSMOS_REST_URL` e `ADDRESS` correspondentes à {API REST COSMOS} da Chain B e {Receiver Chain B}. Por padrão: `COSMOS_REST_URL = "http://localhost:2317"` e `ADDRESS = "ethm1dakgyqjulg29m5fmv992g2y66m9g2mjn6hahwg"`

```
python tests/check_balance_cosmos.py
```

```mermaid
sequenceDiagram
    autonumber
    participant UserA as Usuário Chain A
    participant ChainA as XRPL Sidechain A
    participant Hermes as Relayer Hermes
    participant ChainB as XRPL Sidechain B
    participant UserB as Usuário Chain B

    UserA->>ChainA: Assina e envia MsgTransfer<br/>(axrp, amount, receiver, channel-0)

    ChainA->>ChainA: Valida a transação
    ChainA->>ChainA: Bloqueia axrp nativo
    ChainA-->>Hermes: Emite evento send_packet<br/>(pacote IBC ICS-20)

    Hermes->>ChainA: Consulta prova do pacote
    Hermes->>ChainB: Envia RecvPacket<br/>(pacote + prova)

    ChainB->>ChainB: Verifica prova via light client
    ChainB->>ChainB: Processa pacote ICS-20
    ChainB->>UserB: Credita voucher IBC

    ChainB-->>Hermes: Emite acknowledgement
    Hermes->>ChainA: Relaya acknowledgement

    ChainA->>ChainA: Confirma entrega do pacote
```