# XRPL EVM Sidechains locais com YUI Relayer

Este projeto sobe três chains XRPL EVM locais (`xrplevm-a`, `xrplevm-b` e
`xrplevm-c`) e usa o YUI Relayer para comunicação IBC.


## Pré-requisitos

- Docker;
- Git;
- Python 3;


## 1. Preparar o ambiente Python

No Git Bash do Windows:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

No Linux ou macOS, a ativação é feita com:

```bash
source .venv/bin/activate
```

Confirme que o comando `python` aponta para o ambiente virtual:

```bash
python -c "import sys; print(sys.executable)"
```

## 2. Configurar as variáveis de ambiente

Crie o `.env` a partir do exemplo:

```bash
cp .env.example .env
```

O arquivo define a rede Docker, o IP do YUI e a conta local usada para financiar
as chaves do relayer. Para a configuração padrão, os valores do exemplo podem
ser mantidos.

## 3. Gerar o Docker Compose

O Compose é gerado a partir do `chains.json` e do `.env`:

```bash
python scripts/render_docker_compose.py
```

Execute esse comando novamente sempre que adicionar ou alterar uma chain no
`chains.json`.

## 4. Subir os containers

```bash
docker compose up -d --build
```

Confira o estado:

```bash
docker compose ps
```

O primeiro boot das chains cria o estado local e pode levar alguns instantes. O
script de setup aguarda os RPCs ficarem disponíveis e as chains terminarem a
sincronização.

Opcionalmente, verifique os endpoints da chain A:

```bash
curl http://localhost:26657/status
```

```bash
curl -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1}' \
  http://localhost:8545
```

## 5. Configurar o YUI

### Configuração padrão

```bash
python scripts/setup_yui.py
```

Sem argumentos, o setup:

1. verifica o container YUI e os RPCs de todas as chains;
2. inicializa a configuração global do YUI;
3. gera e registra as chains do `chains.json`;
4. importa as chaves dos relayers;
5. completa cada saldo até 100 XRP, quando necessário;
6. inicializa os light clients locais;
7. registra o path `xrplevm-a-b`;
8. cria ou valida os IBC clients, a connection e o channel;
9. exibe os IDs resultantes.

As etapas que já foram concluídas são reutilizadas ou ignoradas quando possível.
Os arquivos persistentes do YUI ficam em `relayer_config/yui` pelo bind mount do
Compose.

### Argumento `--config`

Configura somente uma chain já declarada no `chains.json`, incluindo arquivo de
configuração, registro no YUI, chave, financiamento e light client:

```bash
python scripts/setup_yui.py --config xrplevm-d
```

Antes disso, inclua a chain no `chains.json`, regenere o Compose e suba seu
container:

```bash
python scripts/render_docker_compose.py
docker compose up -d --build
```

O argumento `--config` não cria um path automaticamente.

### Argumento `--path`

Registra e abre um path entre duas chains já configuradas no YUI. A primeira é
a origem (`src`) e a segunda é o destino (`dst`):

```bash
python scripts/setup_yui.py --path xrplevm-a xrplevm-d
```

Esse comando gera o path `xrplevm-a-d` e cria ou valida seus IBC clients,
connection e channel. Ele não repete a configuração nem o financiamento das
chains.

Para configurar uma nova chain e abrir seu path na mesma execução, combine os
argumentos:

```bash
python scripts/setup_yui.py \
  --config xrplevm-d \
  --path xrplevm-a xrplevm-d
```

Os nomes informados em `--config` e `--path` devem corresponder exatamente ao
campo `name` do `chains.json`.

Para consultar toda a configuração resultante:

```bash
docker exec yui-relayer yrly config show
```

## 6. Iniciar o serviço do YUI

O setup não inicia o serviço do relayer. Em outro terminal, use o nome do path
mostrado ao final da configuração padrão:

```bash
docker exec yui-relayer yrly service start xrplevm-a-b
```

Mantenha esse terminal aberto durante a transferência. Para outro path, substitua
`xrplevm-a-b` pelo nome correspondente, por exemplo `xrplevm-a-d`.

## 7. Preparar o teste de transferência

O arquivo `tests/transfer_cross_chain.py` envia 1 XRP da chain A para a chain B.
Antes de executá-lo, confira estas constantes no início do arquivo:

```python
SOURCE_CHAIN = "Chain A"
SOURCE_CHANNEL = "channel-N"
DESTINATION_CHAIN = "Chain B"
```

Use em `SOURCE_CHANNEL` o channel do endpoint `src` exibido pela etapa final do
setup. O número não é necessariamente `channel-0`: ele depende do estado que já
existe nos volumes.

Se as credenciais ou o destinatário tiverem sido alterados, atualize também
`SOURCE_EVM_PRIVATE_KEY`, `SOURCE_COSMOS_ADDRESS` e
`DESTINATION_COSMOS_ADDRESS` no teste.

## 8. Realizar a transação IBC

Com o serviço YUI ativo no outro terminal, execute:

```bash
python tests/transfer_cross_chain.py
```

Uma submissão aceita pela chain de origem apresenta `Code: 0` e um `TxHash`, por
exemplo:

```json
{
  "Source Chain": "Chain A",
  "Source Chain ID": "xrplevm_1450001-1",
  "Destination Chain": "Chain B",
  "Destination Chain ID": "xrplevm_1450002-1",
  "Source Port": "transfer",
  "Source Channel": "channel-N",
  "Amount": "1 XRP",
  "Code": 0,
  "TxHash": "..."
}
```

O resultado também é acrescentado a `tests/logfile.jsonl`. Aguarde o YUI relayar
o pacote e o acknowledgement.

## 9. Conferir o saldo no destino

O script abaixo consulta, por padrão, o endereço de destino na REST API da chain
B:

```bash
python utils/check_balance_cosmos.py
```

Também é possível consultar diretamente:

```bash
curl http://localhost:2317/cosmos/bank/v1beta1/balances/ethm1dakgyqjulg29m5fmv992g2y66m9g2mjn6hahwg
```

Uma transferência IBC recebida pode aparecer como voucher com denominação
`ibc/<hash>`, além dos saldos nativos em `axrp`.

## Encerrar o ambiente

Interrompa o processo `yrly service start` com `Ctrl+C` e depois execute:

```bash
docker compose down
```

Os volumes nomeados das chains e o diretório `relayer_config/yui` preservam o
estado para a próxima execução.
