# Container image for running the agent as a gateway (the primary field target is a systemd service
# on a Raspberry Pi, packaged as a .deb; this image is what the fleet simulator and the backend/web
# repos' E2E and load tests point at). Run `docker run <img> fleet --config fleet.yaml` for the
# device-simulator role, or `run` for a single agent.

FROM python:3.12-slim AS builder

ARG EXTRA_CA_CERT=""
COPY --from=ghcr.io/astral-sh/uv:0.12 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev


FROM python:3.12-slim AS runtime

ARG EXTRA_CA_CERT=""
RUN if [ -n "$EXTRA_CA_CERT" ]; then \
        echo "$EXTRA_CA_CERT" > /usr/local/share/ca-certificates/extra.crt && \
        update-ca-certificates; \
    fi && \
    groupadd --system app && useradd --system --gid app --home /app app

ENV PATH="/app/.venv/bin:$PATH" \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    PYTHONUNBUFFERED=1

LABEL org.opencontainers.image.title="aurora-sensor-agent" \
      org.opencontainers.image.description="Aurora Clinic cold-chain sensor agent and fleet simulator" \
      org.opencontainers.image.source="https://github.com/aurora-clinic/aurora-sensor-agent" \
      org.opencontainers.image.licenses="MIT"

WORKDIR /app
COPY --from=builder --chown=app:app /app /app
USER app

ENTRYPOINT ["aurora-agent"]
# Default role: run the whole virtual fleet from the bundled fleet.yaml (the device-simulator).
# Override with `docker run <img> run` for a single agent, or `sim` for the driver only.
CMD ["fleet", "--config", "fleet.yaml", "--cycles", "20"]
