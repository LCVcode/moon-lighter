FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        git \
        jq \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent@0.85.1

RUN useradd --create-home --shell /bin/bash moon
USER moon
WORKDIR /workspace

ENTRYPOINT ["pi"]
