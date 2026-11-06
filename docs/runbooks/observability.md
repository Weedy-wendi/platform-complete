# OTLP, Prometheus and Grafana

The observability overlay adds an OTLP collector, Tempo (traces), Prometheus
(metrics) and Grafana (dashboards).

## Start

```bash
docker compose \
  -f deploy/compose.yaml \
  -f deploy/compose.observability.yaml \
  up -d
```

| Component | URL |
|---|---|
| OTLP HTTP | `http://localhost:4318` |
| OTLP gRPC | `http://localhost:4317` |
| Prometheus | `http://localhost:9090` |
| Tempo | `http://localhost:3200` |
| Grafana | `http://localhost:3000` |

Set `GRAFANA_ADMIN_PASSWORD` before starting; the default is a placeholder.

## Application configuration

Point every service that emits telemetry at the collector:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4318"
export OTEL_SERVICE_NAME="pingce-platform"
```

The MCP server exposes `/metrics` on its HTTP port; the API exposes `/metrics`
too. Prometheus scrapes both plus the collector's Prometheus exporter.

## Dashboards and alerts

- Provisioned datasources: Prometheus (default) and Tempo.
- Provisioned dashboards: `deploy/grafana/dashboards/*.json`
  (platform, queue, errors, latency, cost).
- Alert rules: `deploy/prometheus/alerts.yaml`.

## Verify

```bash
curl -s http://localhost:9090/-/ready
curl -s http://localhost:3000/api/health
curl -s http://localhost:4318/v1/traces -o /dev/null -w '%{http_code}\n'
```

Open Grafana > Pingce to see the four operational dashboards. If traces do not
appear, check `docker compose logs otel-collector tempo`.
