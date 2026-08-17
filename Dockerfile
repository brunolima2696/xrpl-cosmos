FROM golang:1.23.8

RUN apt update && apt install -y \
    git \
    make \
    jq \
    curl \
    build-essential \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone https://github.com/xrplevm/node.git .

RUN make build

RUN sed -i '/^[[:space:]]*make build[[:space:]]*$/d' local-node.sh && \
    sed -i 's#unbonding_time"]="60s"#unbonding_time"]="86400s"#g' local-node.sh && \
    chmod +x local-node.sh

RUN sed -i '/bin\/exrpd start \\/i\
sed -i '\''s#laddr = "tcp://127.0.0.1:26657"#laddr = "tcp://0.0.0.0:26657"#g'\'' "$CONFIG"\n\
sed -i '\''s#address = "127.0.0.1:8545"#address = "0.0.0.0:8545"#g'\'' "$APP_TOML"\n\
sed -i '\''s#ws-address = "127.0.0.1:8546"#ws-address = "0.0.0.0:8546"#g'\'' "$APP_TOML"\n\
sed -i '\''s#address = "tcp://localhost:1317"#address = "tcp://0.0.0.0:1317"#g'\'' "$APP_TOML"\n\
sed -i '\''s#address = "localhost:9090"#address = "0.0.0.0:9090"#g'\'' "$APP_TOML"' local-node.sh

COPY scripts/start-persistent.sh /usr/local/bin/start-persistent.sh

RUN sed -i 's/\r$//' /usr/local/bin/start-persistent.sh && \
    chmod +x /usr/local/bin/start-persistent.sh

EXPOSE 26656 26657 1317 9090 8545 8546