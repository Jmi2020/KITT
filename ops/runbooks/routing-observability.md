# KITTY Routing Observability Runbook

## Dashboards

- **Routing Overview** (`ops/dashboards/routing.json`): panels for per-tier request volume, latency p95, local handling ratio, and cumulative cost.

## Metrics

- `kitty_routing_requests_total{tier}` – counter of routing decisions.
- `kitty_routing_latency_ms_bucket` – histogram for latency percentiles.
- `kitty_routing_cost_total{tier}` – accumulated estimated spend.
- `kitty_routing_local_ratio` – gauge reflecting rolling local handling percentage.

## Alerts (future)

- Local ratio < 0.7 for 5 minutes.
- Routing latency p95 > 1500 ms.
- Frontier tier usage spikes > 10 requests per minute.

## Procedures

1. Inspect dashboard when routing escalations increase.
2. Review audit logs via `/api/routing/logs` for anomalies.
3. Tune thresholds in `services/brain/src/brain/routing/config.py` as needed.
4. Update cost heuristics in `services/brain/src/brain/routing/router.py` if provider pricing changes.
