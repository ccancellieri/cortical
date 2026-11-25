# syntax=docker/dockerfile:1
# Cortical MCP Server (Zero-Dependency Python 3.10+ Stdlib Only)
# Containerized for Glama.ai inspection and reproducible local/CI execution.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Cortical MCP Server" \
      org.opencontainers.image.description="Zero-server, stdlib-only MCP server with fail-closed Privacy Vault, lossless TOON compression, hardware preflight, ROI telemetry, cross-harness handoff, and Prompt Studio." \
      org.opencontainers.image.source="https://github.com/ccancellieri/cortical" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.authors="Carlo Cancellieri <https://github.com/ccancellieri>"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    HOME=/tmp/cortical-home \
    CORTICAL_VAULT_DB=/tmp/cortical-home/.cortical_data/vault.db

WORKDIR /app

COPY pyproject.toml LICENSE NOTICE README.md glama.json server.json ./
COPY src ./src

# Run as an unprivileged user with a writable ephemeral home directory so
# Glama and MCP inspectors can boot and list tools/resources/prompts without
# API keys, external services, or root privileges.
RUN addgroup --system --gid 10001 cortical \
    && adduser --system --uid 10001 --ingroup cortical --home /tmp/cortical-home cortical \
    && mkdir -p /tmp/cortical-home/.cortical_data \
    && chown -R cortical:cortical /app /tmp/cortical-home

USER cortical

ENTRYPOINT ["python3", "-m", "cortical.mcp_server"]
