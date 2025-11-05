# KITT

Initial repository for the KITT project.

## Project layout

- `infra/compose/` — Docker Compose stack for local orchestration (API services, MQTT, Redis, Postgres, MinIO, Prometheus/Grafana, Loki, Tempo, Home Assistant).
- `services/` — Service code; shared Python utilities live under `services/common`.
- `specs/001-KITTY/` — Current feature specification, plan, data model, contracts, quickstart flows, and tasks.
- `Reference/` — External reference material (ignored from git history).

## Getting started

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Configure environment
cp infra/compose/.env.example infra/compose/.env
```

Run the docker stack:

```bash
docker compose -f infra/compose/docker-compose.yml up -d --build
```

Run migrations for shared models:

```bash
alembic -c services/common/alembic.ini upgrade head
```

Stop services:

```bash
docker compose -f infra/compose/docker-compose.yml down
```

## Continuous Integration

GitHub Actions validate Python imports and lint the shared utilities, and ensure the Docker Compose definition remains valid.
