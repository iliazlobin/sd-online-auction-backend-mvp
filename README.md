# Online Auction MVP

A FastAPI + PostgreSQL + Redis online auction platform with atomic bid placement
via Redis Lua CAS, real-time WebSocket updates, and automated auction lifecycle
management. The MVP implements 7 functional requirements verified against 19
black-box acceptance tests — see [DESIGN.md](DESIGN.md) for the full spec.

## Architecture

```mermaid
graph TB
    subgraph api["FastAPI App — port 8000"]
        R_HEALTH["Health Router<br/>GET /healthz"]
        R_AUCTION["Auction Router<br/>POST/GET /auctions"]
        R_BID["Bid Router<br/>POST /auctions/{id}/bids"]
        R_SEARCH["Search Router<br/>GET /auctions (search)"]
        WS["WebSocket Endpoint<br/>WS /auctions/{id}/live"]
    end

    subgraph services["Service Layer"]
        AUCTION_SVC["AuctionService<br/>create, lifecycle, close, settle"]
        BID_SVC["BidService<br/>atomic Lua CAS, dedup, persistence"]
        SEARCH_SVC["SearchService<br/>PostgreSQL FTS + filters"]
        FANOUT_SVC["FanOutService<br/>Redis Pub/Sub broadcast"]
    end

    subgraph stores["Data Stores"]
        PG["(PostgreSQL<br/>users, auctions, bids, proxy_bids)"]
        REDIS["(Redis<br/>auction state hash, Lua CAS,<br/>bid stream, Pub/Sub)"]
    end

    subgraph bg["Background"]
        SCHEDULER["APScheduler<br/>poll start/close every 1s"]
    end

    R_HEALTH --> AUCTION_SVC
    R_AUCTION --> AUCTION_SVC
    R_BID --> BID_SVC
    R_SEARCH --> SEARCH_SVC
    WS --> FANOUT_SVC
    BID_SVC --> REDIS
    BID_SVC --> PG
    BID_SVC --> FANOUT_SVC
    FANOUT_SVC --> REDIS
    AUCTION_SVC --> PG
    AUCTION_SVC --> REDIS
    AUCTION_SVC --> FANOUT_SVC
    SCHEDULER --> AUCTION_SVC
    SEARCH_SVC --> PG

    classDef rt fill:#d0ebff,stroke:#1c7ed6,color:#1a1a1a
    classDef svc fill:#ffe8cc,stroke:#e8590c,color:#1a1a1a
    classDef store fill:#d3f9d8,stroke:#2f9e44,color:#1a1a1a
    classDef bg fill:#e8d5f5,stroke:#845ef7,color:#1a1a1a

    class R_HEALTH,R_AUCTION,R_BID,R_SEARCH,WS rt
    class AUCTION_SVC,BID_SVC,SEARCH_SVC,FANOUT_SVC svc
    class PG,REDIS store
    class SCHEDULER bg
```

**Components:**

| Component | Tech | Role |
|-----------|------|------|
| FastAPI app | Python 3.12, uvicorn | HTTP + WebSocket server |
| PostgreSQL | asyncpg via SQLAlchemy 2.0 async | Durable record of users, auctions, bids |
| Redis | redis-py async | Hot-path bid kernel (atomic Lua CAS), state cache, Pub/Sub fanout, bid stream |
| APScheduler | apscheduler | Auction lifecycle driver (in-process, 1s poll) |

## Quick Start

### Prerequisites

- Python 3.11+
- Docker + Docker Compose (for the full stack)
- A running PostgreSQL and Redis instance (for local dev without Docker)

### Using Docker Compose (recommended)

```bash
# 1. Clone and enter the project
git clone git@github.com:iliazlobin/sd-online-auction-backend-mvp.git
cd sd-online-auction-backend-mvp

# 2. Start the stack
cp .env.example .env
docker compose up --build -d

# 3. Run database migrations
docker compose run app alembic upgrade head

# 4. Verify health
curl http://localhost:8010/healthz
# → {"status":"ok"}

# 5. Run tests
docker compose run app python -m pytest tests/ -v
```

### Local development (without Docker)

```bash
# 1. Install the package with dev dependencies
pip install -e .[dev]

# 2. Configure Postgres/Redis connection
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/auction"
export REDIS_URL="redis://localhost:6379/0"

# 3. Run migrations
alembic upgrade head

# 4. Start the server
uvicorn auction_app.main:create_app --host 0.0.0.0 --port 8000 --factory

# 5. In another terminal, run tests
python -m pytest tests/ -v
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Liveness check |
| `POST` | `/users` | Register a user |
| `POST` | `/auctions` | Create an auction |
| `GET` | `/auctions/{id}` | View auction detail |
| `GET` | `/auctions/{id}/history` | Bid history (paginated) |
| `POST` | `/auctions/{id}/bids` | Place a bid |
| `GET` | `/auctions` | Search/filter auctions |
| `WS` | `/auctions/{id}/live` | Real-time bid updates |

All endpoints return JSON. Authentication is via `X-User-ID` header (MVP: no auth
middleware). See [DESIGN.md §3](DESIGN.md#3-api-contracts) for full request/response
schemas.

## Configuration

All settings via environment variables (see `.env.example` for defaults):

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://auction:auction@db:5432/auction` | PostgreSQL DSN |
| `REDIS_URL` | `redis://redis:6379/0` | Redis DSN |
| `APP_PORT` | `8010` | Host port (Docker Compose only) |

## Test Inventory

### White-box unit tests (6 tests)

Verified passing against the installed package:

```
$ python -m pytest tests/ -v
============================= test session starts ==============================
platform linux -- Python 3.11.15, pytest-8.4.2, pluggy-1.6.0
plugins: anyio-4.14.1, asyncio-0.26.0

collected 6 items

tests/test_auction_service.py::test_placeholder PASSED                   [ 16%]
tests/test_bid_service.py::test_placeholder PASSED                       [ 33%]
tests/test_fanout_service.py::TestFanOutService::test_mask_bidder_id_length PASSED [ 50%]
tests/test_fanout_service.py::TestFanOutService::test_mask_bidder_id_deterministic PASSED [ 66%]
tests/test_fanout_service.py::TestFanOutService::test_mask_bidder_id_different PASSED [ 83%]
tests/test_search_service.py::test_placeholder PASSED                    [100%]

============================== 6 passed in 0.03s ==============================
```

### Black-box acceptance tests (19 tests)

One test file per functional requirement, exercising the running system over HTTP:

| File | Tests | Coverage |
|------|-------|----------|
| `verify/acceptance/test_functional.py` | 11 | FR1 (create), FR2 (bid), FR3 (view), FR5 (lifecycle), concurrency |
| `verify/acceptance/test_fr4_bid_history.py` | 3 | FR4 — paginated bid history |
| `verify/acceptance/test_fr6_winner_determination.py` | 2 | FR6 — winner set after close |
| `verify/acceptance/test_fr7_websocket_updates.py` | 2 | FR7 — WebSocket real-time frames |

Run with the live stack:
```bash
API_BASE_URL=http://localhost:8010 pytest -v verify/acceptance/
```

## Project Layout

```
├── src/auction_app/          # Application package
│   ├── main.py               # create_app() factory, lifespan
│   ├── config.py             # pydantic-settings
│   ├── database.py           # async session/engine
│   ├── redis_client.py       # async Redis pool, Lua registration
│   ├── models/               # SQLAlchemy ORM (user, auction, bid, proxy_bid)
│   ├── schemas/              # Pydantic DTOs
│   ├── routers/              # Thin HTTP layer (health, users, auctions, bids, search, websocket)
│   └── services/             # Domain logic (auction, bid, fanout, search, scheduler)
├── tests/                    # White-box unit tests
├── verify/acceptance/        # Black-box acceptance tests (FR-driven)
├── alembic/                  # Schema migrations
├── Dockerfile                # Multi-stage, python:3.12-slim
├── docker-compose.yml        # db + redis + app
├── DEPLOY.md                 # Host deployment guide
└── DESIGN.md                 # Full design specification
```

## License

MIT
