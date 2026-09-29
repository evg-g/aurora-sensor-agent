"""Bring up the real stack for the software-in-the-loop tier.

The SIL tier proves the agent talks to the *real* backend, not a fake: it starts Postgres, Redis, a
Mosquitto broker, the built ``appointments-api`` image (serving HTTP and, as a second container, its
MQTT ingestion worker), then provisions a device and lets the tests publish telemetry and read it
back through the API.

Everything is skipped cleanly when Docker is unavailable or the API image has not been built, so the
rest of the suite (and a fork's CI without the sibling repo) stays green — the same "skip without
inputs" pattern the deploy jobs use.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import pytest

API_IMAGE = "appointments-api:local"
DB_URL = "postgresql+psycopg://aurora:aurora@db:5432/aurora"
REDIS_URL = "redis://redis:6379/0"
_SERVE_CMD = (
    'sh -c "alembic upgrade head && '
    'uvicorn appointments_api.main:app --host 0.0.0.0 --port 8000"'
)


@dataclass(frozen=True)
class SilStack:
    """Connection info the tests need, all reachable from the host."""

    api_url: str
    mqtt_host: str
    mqtt_port: int
    admin_token: str
    clinic_id: str


def _docker_ready() -> bool:
    try:
        import docker
    except ImportError:
        return False
    try:
        client = docker.from_env()
        client.ping()
        client.images.get(API_IMAGE)
    except Exception:
        return False
    return True


def _wait_for_ready(url: str, timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{url}/health/ready", timeout=5.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(1.0)
    raise TimeoutError(f"API did not become ready at {url} within {timeout}s (last: {last_error})")


@pytest.fixture(scope="session")
def sil_stack(tmp_path_factory: pytest.TempPathFactory) -> Iterator[SilStack]:
    if not _docker_ready():
        pytest.skip(f"Docker unavailable or {API_IMAGE} not built; skipping SIL tier")

    from testcontainers.core.container import DockerContainer
    from testcontainers.core.network import Network
    from testcontainers.core.waiting_utils import wait_for_logs

    conf = tmp_path_factory.mktemp("mosquitto") / "mosquitto.conf"
    conf.write_text("listener 1883 0.0.0.0\nallow_anonymous true\n", encoding="utf-8")

    network = Network()
    network.create()
    started: list[DockerContainer] = []

    def _start(container: DockerContainer, alias: str) -> DockerContainer:
        container.with_network(network).with_network_aliases(alias)
        container.start()
        started.append(container)
        return container

    try:
        postgres = (
            DockerContainer("postgres:16")
            .with_env("POSTGRES_USER", "aurora")
            .with_env("POSTGRES_PASSWORD", "aurora")
            .with_env("POSTGRES_DB", "aurora")
        )
        _start(postgres, "db")
        wait_for_logs(postgres, "database system is ready to accept connections", timeout=60)

        redis = DockerContainer("redis:7")
        _start(redis, "redis")
        wait_for_logs(redis, "Ready to accept connections", timeout=30)

        mosquitto = (
            DockerContainer("eclipse-mosquitto:2")
            .with_exposed_ports(1883)
            .with_volume_mapping(str(conf), "/mosquitto/config/mosquitto.conf", "ro")
        )
        _start(mosquitto, "mosquitto")
        wait_for_logs(mosquitto, "mosquitto version 2", timeout=30)

        api = (
            DockerContainer(API_IMAGE)
            .with_command(_SERVE_CMD)
            .with_env("DATABASE_URL", DB_URL)
            .with_env("REDIS_URL", REDIS_URL)
            .with_env("APP_ENV", "ci")
            .with_env("JWT_SECRET", "dev-only-insecure-change-me")
            .with_env("RATE_LIMIT_ENABLED", "false")
            .with_exposed_ports(8000)
        )
        _start(api, "api")
        api_url = f"http://{api.get_container_host_ip()}:{api.get_exposed_port(8000)}"
        _wait_for_ready(api_url)

        # Seed the demo admin + clinics inside the API container (reads DATABASE_URL from its env).
        code, output = api.get_wrapped_container().exec_run("python scripts/seed.py")
        if code != 0:
            raise RuntimeError(f"seed failed ({code}): {output.decode(errors='replace')}")

        worker = (
            DockerContainer(API_IMAGE)
            .with_command("python -m appointments_api.workers.telemetry_mqtt")
            .with_env("DATABASE_URL", DB_URL)
            .with_env("REDIS_URL", REDIS_URL)
            .with_env("APP_ENV", "ci")
            .with_env("MQTT_BROKER_HOST", "mosquitto")
            .with_env("MQTT_BROKER_PORT", "1883")
        )
        _start(worker, "worker")
        wait_for_logs(worker, "subscribed", timeout=60)

        token = _login(api_url)
        clinic_id = _first_clinic_id(api_url, token)

        yield SilStack(
            api_url=api_url,
            mqtt_host=mosquitto.get_container_host_ip(),
            mqtt_port=int(mosquitto.get_exposed_port(1883)),
            admin_token=token,
            clinic_id=clinic_id,
        )
    finally:
        for container in reversed(started):
            with contextlib.suppress(Exception):
                container.stop()
        with contextlib.suppress(Exception):
            network.remove()


def _login(api_url: str) -> str:
    response = httpx.post(
        f"{api_url}/api/v1/auth/login",
        json={"email": "admin@aurora-clinic.com", "password": "password123"},
        timeout=10.0,
    )
    response.raise_for_status()
    token: str = response.json()["access_token"]
    return token


def _first_clinic_id(api_url: str, token: str) -> str:
    response = httpx.get(
        f"{api_url}/api/v1/clinics",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    response.raise_for_status()
    clinic_id: str = response.json()["data"][0]["id"]
    return clinic_id


@dataclass(frozen=True)
class ProvisionedDevice:
    device_id: str
    secret: str
    clinic_id: str


@pytest.fixture
def provisioned_device(sil_stack: SilStack) -> ProvisionedDevice:
    """Provision a fresh device via the admin API for one test (isolated series)."""
    response = httpx.post(
        f"{sil_stack.api_url}/api/v1/devices",
        headers={"Authorization": f"Bearer {sil_stack.admin_token}"},
        json={
            "clinic_id": sil_stack.clinic_id,
            "location_label": "SIL fridge",
            "hardware_version": "sht4x-rev-c",
            "firmware_version": "1.0.0",
        },
        timeout=10.0,
    )
    response.raise_for_status()
    body = response.json()
    return ProvisionedDevice(
        device_id=body["device"]["id"],
        secret=body["secret"],
        clinic_id=sil_stack.clinic_id,
    )


def poll_timeseries_points(api_url: str, token: str, device_id: str, timeout: float = 30.0) -> int:
    """Poll the device time-series until it has points, returning the sample count. 0 on timeout."""
    deadline = time.monotonic() + timeout
    headers = {"Authorization": f"Bearer {token}"}
    while time.monotonic() < deadline:
        response = httpx.get(
            f"{api_url}/api/v1/devices/{device_id}/telemetry",
            headers=headers,
            params={"bucket": "1m", "agg": "avg"},
            timeout=10.0,
        )
        response.raise_for_status()
        points = response.json()["points"]
        total = sum(p["sample_count"] for p in points)
        if total > 0:
            return int(total)
        time.sleep(1.0)
    return 0
