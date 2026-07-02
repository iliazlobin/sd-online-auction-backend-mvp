# Deploy — Online Auction MVP

## Prerequisites

- **Docker** (with Compose V2 plugin) — [install guide](https://docs.docker.com/engine/install/)
- **Git** (to clone the repository)
- **curl** (for health checks)
- Port **8010** free on the host (configurable via `APP_PORT`)

## Quick Start

```bash
# 1. Clone
git clone <repo-url> online-auction-mvp
cd online-auction-mvp

# 2. Create environment from template
cp .env.example .env

# 3. Build and start all services
docker compose up --build -d --wait

# 4. Run database migrations
docker compose run app alembic upgrade head

# 5. Verify it's alive
curl -sf http://localhost:8010/healthz
# Expected: {"status":"ok"}
```

## Step-by-step

### 1. Environment

Copy the example env file — all keys are commented with safe defaults for
the Docker Compose stack. Only override if your setup differs.

```bash
cp .env.example .env
```

Key configuration variables:

| Variable       | Default                                                   | Description                          |
|----------------|-----------------------------------------------------------|--------------------------------------|
| `APP_PORT`     | `8010`                                                    | Host port mapped to the app          |
| `DATABASE_URL` | `postgresql+asyncpg://auction:auction@db:5432/auction`    | PostgreSQL async DSN                 |
| `REDIS_URL`    | `redis://redis:6379/0`                                    | Redis connection string              |
| `HOST`         | `0.0.0.0`                                                 | uvicorn bind address                 |
| `PORT`         | `8000`                                                    | uvicorn listen port (inside container) |

### 2. Build & Start

```bash
docker compose up --build -d --wait
```

This starts three containers:
- **db** — PostgreSQL 17 (Alpine)
- **redis** — Redis 7 (Alpine)
- **app** — FastAPI application (built from Dockerfile)

The `--wait` flag blocks until all services pass their health checks.
Postgres (`pg_isready`) and Redis (`redis-cli ping`) have health checks
that must pass before the app starts. The app has a `curl /healthz`
health check with a 5-second start period.

### 3. Run Migrations

Alembic owns the schema — never use `create_all()`.

```bash
docker compose run app alembic upgrade head
```

This creates all tables (users, auctions, bids, proxy_bids) with indexes,
constraints, and the full-text search vector column on auctions.

To verify migration state:

```bash
docker compose run app alembic current
```

### 4. Health Check

```bash
curl -sf http://localhost:8010/healthz
```

A healthy response:

```json
{"status":"ok"}
```

## Running Tests

### White-box unit tests (import app modules)

Requires a running Postgres and Redis (or use `host.docker.internal`).
From the Docker Compose stack:

```bash
docker compose exec app pytest tests/ -v
```

### Black-box acceptance tests (HTTP only, no app imports)

Requires the stack to be up and port 8010 reachable:

```bash
API_BASE_URL=http://localhost:8010 pytest verify/acceptance/ -v
```

## Viewing Logs

```bash
# All services
docker compose logs --tail=100

# Follow new logs
docker compose logs -f

# Single service
docker compose logs app --tail=50
```

## Teardown

Stop and remove containers, networks, and volumes (destroys all data):

```bash
docker compose down --volumes --remove-orphans
```

To stop without destroying data:

```bash
docker compose stop
# Restart later: docker compose start
```

## Ports

| Host Port | Service       | Notes                                      |
|-----------|---------------|--------------------------------------------|
| `8010`    | FastAPI app   | Configurable via `APP_PORT` env variable.  |
| (none)    | PostgreSQL    | Compose network only — not published.      |
| (none)    | Redis         | Compose network only — not published.      |

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   FastAPI    │◄──►│  PostgreSQL  │    │    Redis     │
│   :8000      │    │  :5432       │    │  :6379       │
│              │    │  (compose)   │    │  (compose)   │
└──────────────┘    └──────────────┘    └──────────────┘
     :8010 (host)
```

- **FastAPI** serves the API on port 8000 inside the container, mapped to
  `${APP_PORT:-8010}` on the host.
- **PostgreSQL** stores auction, user, bid, and proxy_bid records. No host
  port — accessed by the app over the compose network.
- **Redis** stores auction state hashes, bid streams, Pub/Sub fan-out
  channels, and dedup keys. No host port.

## Troubleshooting

### `app` crashes with `ModuleNotFoundError`

```bash
docker compose run app alembic upgrade head
```

### Port collision

```bash
APP_PORT=8011 docker compose up --build -d --wait
```

### Database not connecting

```bash
docker compose logs db
```

### Redis not connecting

```bash
docker compose logs redis
```

### App health check fails

```bash
docker compose logs app
```
