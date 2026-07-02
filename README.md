# Online Auction MVP

FastAPI + PostgreSQL + Redis online auction platform.

## Stack

- **FastAPI** (async, Python 3.12)
- **PostgreSQL 17** (asyncpg via SQLAlchemy 2.0 async)
- **Redis 7** (atomic Lua CAS for bid placement, Pub/Sub for real-time updates)
- **APScheduler** (auction lifecycle driver)
- **Alembic** (schema migrations)

## Quick Start

```bash
# 1. Start the stack
docker compose up --build -d

# 2. Run migrations
docker compose run app alembic upgrade head

# 3. Check health
curl http://localhost:8010/healthz

# 4. Run tests (without Docker, requires local Postgres + Redis or SQLite mock)
pip install -e .[dev]
pytest
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Liveness check |
| POST | `/users` | Register a user |
| POST | `/auctions` | Create an auction |
| GET | `/auctions` | Search/filter auctions |
| GET | `/auctions/{id}` | Auction detail |
| GET | `/auctions/{id}/history` | Bid history |
| POST | `/auctions/{id}/bids` | Place a bid |
| WS | `/auctions/{id}/live` | Real-time bid updates |

## Configuration

Copy `.env.example` to `.env` and adjust. All settings have safe defaults
for the Docker Compose stack.
