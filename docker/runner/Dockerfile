FROM node:22-bookworm-slim

ARG PI_VERSION=0.85.1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        jq \
        python3 \
        python3-pip \
        python3-venv \
        python-is-python3 \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR=/usr/local/bin sh \
    && uv venv /opt/moon/python-tools \
    && uv pip install --python /opt/moon/python-tools/bin/python ruff ty \
    && ln -s /opt/moon/python-tools/bin/ruff /usr/local/bin/ruff \
    && ln -s /opt/moon/python-tools/bin/ty /usr/local/bin/ty

RUN npm install -g --ignore-scripts "@earendil-works/pi-coding-agent@${PI_VERSION}"

COPY skills/ /opt/moon/skills/

RUN useradd --create-home --shell /bin/bash moon
USER moon
WORKDIR /workspace

ENTRYPOINT ["pi"]
