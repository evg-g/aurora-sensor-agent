# `tests/sil/` — software-in-the-loop (needs Docker + the API image)

This is the only tier that leaves the laptop. It brings up the real stack with testcontainers —
Postgres, Redis, a Mosquitto broker, the built `appointments-api` image serving HTTP, and a second
container running that image's MQTT ingestion worker — then drives the agent's real transports end to
end and reads the telemetry back through the API:

- `test_http_batch_is_ingested_end_to_end` — the real `HttpTransport` posts a real batch to
  `POST /devices/{id}/telemetry:batch`; the API's time-series endpoint then shows the points.
- `test_agent_over_mqtt_is_ingested_end_to_end` — the whole `SensorAgent` (simulated sensor, real
  `MqttTransport`) publishes to the broker; the worker ingests it; the time-series shows the points.

Prerequisites: Docker running and `appointments-api:local` built (`docker build -t appointments-api:local ../appointments-api`). Without them the tier **skips cleanly**, so `make ci-local` on a bare
laptop stays green. Run it with `make sil`.
