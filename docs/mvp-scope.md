# Online Auction MVP — Architecture & Module Layout

A FastAPI-based online auction platform implementing core bidding logic with
Redis-backed atomic Lua CAS for bid consistency. The MVP simplifies the full
system design (Notion `38fd8650`) by replacing Kafka with Redis Streams for bid
ordering, using PostgreSQL full-text search instead of a dedicated search index,
collapsing proxy bidding to a store-only model, and running APScheduler as the
auction lifecycle driver.

## Architecture

```mermaid
graph TB
    subgraph api["FastAPI App — port 8000"]
        R_HEALTH[Health Router<br/>GET /healthz]
        R_AUCTION[Auction Router<br/>POST/GET /auctions]
        R_BID[Bid Router<br/>POST /auctions/{id}/bids]
        R_SEARCH[Search Router<br/>GET /auctions]
        WS[WebSocket Endpoint<br/>WS /auctions/{id}/live]
    end

    subgraph services["Service Layer"]
        AUCTION_SVC[AuctionService<br/>create, lifecycle, close]
        BID_SVC[BidService<br/>atomic CAS, dedup, proxy store]
        SEARCH_SVC[SearchService<br/>PostgreSQL FTS + filters]
        FANOUT_SVC[FanOutService<br/>Redis Pub/Sub broadcast]
    end

    subgraph stores["Data Stores"]
        PG[(PostgreSQL<br/>auctions, bids, users, proxy_bids)]
        REDIS[(Redis<br/>auction state hash, CAS Lua,<br/>bid stream, Pub/Sub)]
    end

    subgraph bg["Background Tasks"]
        SCHEDULER[APScheduler<br/>lifecycle: start/close auctions]
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
    SCHEDULER --> AUCTION_SVC
    SEARCH_SVC --> PG
    AUCTION_SVC --> FANOUT_SVC

    classDef rt fill:#d0ebff,stroke:#1c7ed6,color:#1a1a1a
    classDef svc fill:#ffe8cc,stroke:#e8590c,color:#1a1a1a
    classDef store fill:#d3f9d8,stroke:#2f9e44,color:#1a1a1a
    classDef bg fill:#e8d5f5,stroke:#845ef7,color:#1a1a1a

    class R_HEALTH,R_AUCTION,R_BID,R_SEARCH,WS rt
    class AUCTION_SVC,BID_SVC,SEARCH_SVC,FANOUT_SVC svc
    class PG,REDIS store
    class SCHEDULER bg
```

Routers are thin — they parse HTTP, validate with Pydantic schemas, and delegate
to services. Services own the domain logic, Redis operations, and database access.
APScheduler runs as part of the FastAPI lifespan, firing auction start/close events
at their scheduled times. Redis is the hot-path store: the atomic Lua CAS script
validates and places bids against an auction's state hash, while the bid stream
(`auction:{id}:bids`) provides ordered persistence before PostgreSQL writes.

### MVP scope simplifications (from the full design)

| Full Design Component | MVP Replacement | Rationale |
|---|---|---|
| Kafka (bid ordering) | Redis Streams + direct HTTP path | Single-node, no cross-partition coordination needed |
| Sharded inverted index | PostgreSQL `tsvector` + GIN index | MVP data volume fits in a single indexed table |
| Valkey sharded Pub/Sub | Redis Pub/Sub (single instance) | Single Redis node; no cluster cross-talk at MVP scale |
| ZSET-based scheduler with lease workers | APScheduler (in-process) | Single process; no worker crash failover needed |
| Full proxy resolution engine | Store-only: save proxy_max, no auto-counter-bid | Simplified bid path; proxy increment logic deferred |
| Settlement (fencing token + Stripe) | Mark winner: UPDATE auction SET winner_id, state=SOLD | Payment out of MVP scope |

## Data Model

```sql
"user" {
  user_id:      UUID PK DEFAULT gen_random_uuid()
  display_name: TEXT NOT NULL
  email:        TEXT UNIQUE NOT NULL       ← for auth; simplified (no password hash in MVP)
  created_at:   TIMESTAMPTZ DEFAULT now()
}

auction {
  auction_id:     UUID PK DEFAULT gen_random_uuid()
  seller_id:      UUID NOT NULL REFERENCES "user"(user_id)
  title:          TEXT NOT NULL
  description:    TEXT
  category:       TEXT NOT NULL             ← indexed for FTS + filter
  starting_price: DECIMAL(12,2) NOT NULL CHECK (starting_price > 0)
  reserve_price:  DECIMAL(12,2)             ← nullable; NULL = no reserve
  min_increment:  DECIMAL(12,2) NOT NULL DEFAULT 1.00
  start_ts:       TIMESTAMPTZ NOT NULL
  end_ts:         TIMESTAMPTZ NOT NULL
  state:          TEXT NOT NULL DEFAULT 'UPCOMING'  ← UPCOMING|ACTIVE|CLOSED|SOLD|UNSOLD
  highest_bid:    DECIMAL(12,2)             ← denormalized; also in Redis hash
  winner_id:      UUID REFERENCES "user"(user_id)  ← set at settlement
  created_at:     TIMESTAMPTZ DEFAULT now()

  INDEX ix_auction_state (state)
  INDEX ix_auction_category (category)
  INDEX ix_auction_end_ts (end_ts)          ← scheduler queries
  -- Full-text search index
  -- auction_fts: tsvector GENERATED ALWAYS AS (to_tsvector('english', title || ' ' || coalesce(description, ''))) STORED
  -- GIN index on auction_fts
}

bid {
  bid_id:       UUID PK DEFAULT gen_random_uuid()
  auction_id:   UUID NOT NULL REFERENCES auction(auction_id)
  bidder_id:    UUID NOT NULL REFERENCES "user"(user_id)
  amount:       DECIMAL(12,2) NOT NULL
  is_proxy:     BOOLEAN NOT NULL DEFAULT false
  sequence_num: INTEGER NOT NULL            ← monotonically increasing per auction; from Redis HINCRBY
  status:       TEXT NOT NULL DEFAULT 'ACCEPTED'  ← ACCEPTED|REJECTED
  rejection_reason: TEXT                     ← BID_TOO_LOW|AUCTION_NOT_ACTIVE|AUCTION_ENDED|SELF_OUTBID
  created_ts:   TIMESTAMPTZ DEFAULT now()

  INDEX ix_bid_auction_seq (auction_id, sequence_num DESC)  ← bid history query
  INDEX ix_bid_bidder (bidder_id)           ← user's bid history
  UNIQUE(auction_id, bidder_id, amount, created_ts)  ← soft dedup guard
}

proxy_bid {
  proxy_id:   UUID PK DEFAULT gen_random_uuid()
  auction_id: UUID NOT NULL REFERENCES auction(auction_id)
  bidder_id:  UUID NOT NULL REFERENCES "user"(user_id)
  max_bid:    DECIMAL(12,2) NOT NULL
  active:     BOOLEAN NOT NULL DEFAULT true
  entered_ts: TIMESTAMPTZ DEFAULT now()

  UNIQUE(auction_id, bidder_id)             ← one proxy per bidder per auction
}
```

### Redis data structures

```
auction:{id}  →  HASH
  state:         "ACTIVE"
  highest_bid:   "150.00"
  highest_bidder: "uuid-of-bidder"
  end_ts:        "1719950000"              ← unix timestamp
  sequence_num:  "42"                      ← HINCRBY on each accepted bid
  extensions_used: "2"
  min_increment: "1.00"
  start_ts:      "1719900000"

auction:{id}:bids  →  STREAM               ← ordered bid persistence
  XADD with fields: bid_id, bidder_id, amount, is_proxy, client_ts
  Consumer group: bid_processor
  Awaits Redis CAS result before ACK

bid_result:{bid_id}  →  STRING (NX, TTL=48h)  ← dedup key
  "ACCEPTED" | "REJECTED:BID_TOO_LOW" | ...

fanout:auction:{id}  →  PUB/SUB channel     ← pushed by FanOutService
  { "sequence_num": 42, "current_price": "155.00",
    "high_bidder_masked": "a3f2...", "end_ts": "1719950060" }
```

## API Contracts

All endpoints return JSON. Errors use standard HTTP status codes with a `detail` field.

### `POST /users` — Register a user (MVP bootstrap)

Request:
```json
{"display_name": "Alice", "email": "alice@example.com"}
```

Responses:
- `201 Created` — `{"user_id": "...", "display_name": "Alice", "email": "alice@example.com"}`
- `409 Conflict` — email already registered

### `POST /auctions` — Create an auction listing

Headers: `X-User-ID: <seller_user_id>`

Request:
```json
{
  "title": "Vintage Watch",
  "description": "A 1960s Omega Seamaster",
  "category": "watches",
  "starting_price": 100.00,
  "reserve_price": 500.00,
  "min_increment": 10.00,
  "start_ts": "2026-07-03T12:00:00Z",
  "end_ts": "2026-07-10T12:00:00Z"
}
```

Responses:
- `201 Created` — `{"auction_id": "...", "state": "UPCOMING", ...}`
- `400 Bad Request` — `start_ts` in the past, `end_ts` <= `start_ts`, invalid price
- `404 Not Found` — `X-User-ID` doesn't exist

### `POST /auctions/{auction_id}/bids` — Place a bid

Headers: `X-User-ID: <bidder_user_id>`

Request:
```json
{"amount": 150.00}
```
Optional proxy bid:
```json
{"amount": 110.00, "is_proxy": true, "proxy_max": 500.00}
```

Responses:
- `201 Created` — `{"bid_id": "...", "status": "ACCEPTED", "sequence_num": 5, "current_price": "150.00"}`
- `409 Conflict` — `{"status": "REJECTED", "reason": "BID_TOO_LOW", "current_price": "200.00"}`
- `409 Conflict` — `{"status": "REJECTED", "reason": "AUCTION_NOT_ACTIVE"}`
- `409 Conflict` — `{"status": "REJECTED", "reason": "AUCTION_ENDED"}`
- `422 Unprocessable Entity` — `amount` <= 0, malformed decimal

### `GET /auctions/{auction_id}` — View auction detail

Query params: none

Response `200 OK`:
```json
{
  "auction_id": "...",
  "title": "Vintage Watch",
  "category": "watches",
  "starting_price": "100.00",
  "current_price": "150.00",
  "min_increment": "10.00",
  "bid_count": 5,
  "state": "ACTIVE",
  "start_ts": "2026-07-03T12:00:00Z",
  "end_ts": "2026-07-10T12:00:00Z",
  "time_remaining_seconds": 604740
}
```
- `404` — auction not found

### `GET /auctions/{auction_id}/history` — Bid history

Query params:
- `cursor` (integer, optional) — `sequence_num` to paginate from (newer-first)
- `limit` (integer, default 50, max 100)

Response `200 OK`:
```json
{
  "auction_id": "...",
  "bids": [
    {"bid_id": "...", "bidder_id": "...", "amount": "150.00", "sequence_num": 5, "created_ts": "..."},
    {"bid_id": "...", "bidder_id": "...", "amount": "140.00", "sequence_num": 4, "created_ts": "..."}
  ],
  "next_cursor": 2
}
```

### `GET /auctions` — Search active auctions

Query params:
- `category` (string, optional)
- `price_min` (decimal, optional)
- `price_max` (decimal, optional)
- `q` (string, optional) — full-text search keyword
- `state` (string, default `ACTIVE`) — `ACTIVE`, `UPCOMING`, `CLOSED`, `SOLD`
- `cursor` (string, optional) — base64-encoded pagination token
- `limit` (integer, default 20, max 100)

Response `200 OK`:
```json
{
  "auctions": [...],
  "next_cursor": "...",
  "total": 142
}
```

### `WS /auctions/{auction_id}/live` — Real-time bid updates

WebSocket endpoint. Client connects, receives JSON frames:
```json
{"sequence_num": 6, "current_price": "160.00", "high_bidder_masked": "a3f2...", "end_ts": "1719950060"}
```

On connection, sends current state as the first frame. Bidder identity masked: first 4 chars of `SHA256(bidder_id)` rendered as hex. If the requesting user IS the highest bidder, the full `bidder_id` is included as `is_you: true`.

### `GET /healthz` — Liveness check

Response `200 OK`: `{"status": "ok"}`

## Redis Lua CAS Script

The core bid placement algorithm runs as an atomic Lua script inside Redis. This is
the single consistency kernel — it replaces database row locks, version-based
optimistic locking, and retry storms with a sub-millisecond atomic check-and-set.

```lua
-- auction:place_bid.lua
-- KEYS[1]: auction:{id}        — auction state hash
-- KEYS[2]: bid_result:{bid_id} — dedup key (SET NX)
-- ARGV[1]: bid_id
-- ARGV[2]: bidder_id
-- ARGV[3]: amount             — decimal as string (e.g. "150.00")
-- ARGV[4]: now_ts             — current unix timestamp (seconds)
-- ARGV[5]: dedup_ttl          — seconds until auction close + 48h

local h = redis.call

-- 0. Dedup: if this bid was already processed, return cached result
local cached = h('GET', KEYS[2])
if cached then
    if cached == 'ACCEPTED' then
        return {1, h('HGET', KEYS[1], 'highest_bid'), h('HGET', KEYS[1], 'sequence_num')}
    else
        return {0, cached}
    end
end

-- 1. State check
local state = h('HGET', KEYS[1], 'state')
if state ~= 'ACTIVE' then
    h('SET', KEYS[2], 'AUCTION_NOT_ACTIVE', 'EX', ARGV[5])
    return {0, 'AUCTION_NOT_ACTIVE'}
end

-- 2. Time check
local end_ts = tonumber(h('HGET', KEYS[1], 'end_ts'))
local now = tonumber(ARGV[4])
if now >= end_ts then
    h('SET', KEYS[2], 'AUCTION_ENDED', 'EX', ARGV[5])
    return {0, 'AUCTION_ENDED'}
end

-- 3. Amount check
local current = tonumber(h('HGET', KEYS[1], 'highest_bid') or 0)
local min_inc = tonumber(h('HGET', KEYS[1], 'min_increment'))
local min_bid = current + min_inc
local amount = tonumber(ARGV[3])

-- Self-outbid: bidder is already the highest bidder
local current_bidder = h('HGET', KEYS[1], 'highest_bidder')
if current_bidder == ARGV[2] and amount <= current then
    h('SET', KEYS[2], 'SELF_OUTBID', 'EX', ARGV[5])
    return {0, 'SELF_OUTBID'}
end

if amount < min_bid then
    h('SET', KEYS[2], 'BID_TOO_LOW', 'EX', ARGV[5])
    return {0, 'BID_TOO_LOW'}
end

-- 4. Accept bid: update state atomically
h('HSET', KEYS[1],
  'highest_bid', ARGV[3],
  'highest_bidder', ARGV[2],
  'last_bid_ts', ARGV[4])

local seq = h('HINCRBY', KEYS[1], 'sequence_num', 1)

-- 5. Anti-snipe extension (MVP: simplified — single 60s extension, max 5)
local ext_window = 60
local max_ext = 5
if (end_ts - now) < ext_window then
    local ext_used = tonumber(h('HGET', KEYS[1], 'extensions_used') or 0)
    if ext_used < max_ext then
        local new_end = end_ts + ext_window
        h('HSET', KEYS[1], 'end_ts', new_end, 'extensions_used', ext_used + 1)
    end
end

-- 6. Mark dedup key as accepted
h('SET', KEYS[2], 'ACCEPTED', 'EX', ARGV[5])

return {1, ARGV[3], seq, h('HGET', KEYS[1], 'end_ts')}
```

Return value convention: `{status, ...}` where `status=1` means accepted, `status=0` means rejected with reason string.

## Service Layer Breakdown

### `AuctionService` — `src/auction_app/services/auction_service.py`

Lifecycle owner. Creates auction records in PostgreSQL, initializes Redis hash on
auction start, transitions state on close, marks winner at settlement.

Key methods:
- `create_auction(db, seller_id, data) -> Auction` — INSERT + register in scheduler
- `start_auction(auction_id) -> None` — initialize Redis hash with state=ACTIVE, sequence_num=0, highest_bid=0
- `close_auction(auction_id) -> None` — read winner from Redis, UPDATE PostgreSQL (state=CLOSED, winner_id, final_price)
- `get_auction(db, redis, auction_id) -> AuctionDetail` — merge PostgreSQL metadata + Redis current state
- `resolve_settlement(auction_id) -> None` — check reserve price, mark SOLD/UNSOLD

Tier: **staff-engineer** — correctness-critical lifecycle transitions

### `BidService` — `src/auction_app/services/bid_service.py`

The hot-path service. Evaluates bids via the atomic Lua CAS script, persists
accepted/rejected bids to PostgreSQL, publishes fan-out events.

Key methods:
- `place_bid(redis, db, auction_id, bidder_id, amount, is_proxy, proxy_max) -> BidResult`
  1. Generate `bid_id` (UUID v4)
  2. XADD to `auction:{id}:bids` stream (durable record before CAS)
  3. EVAL the Lua CAS script
  4. On ACCEPTED: INSERT into `bid` table with `sequence_num` from Redis, PUBLISH to `fanout:auction:{id}`
  5. On REJECTED: INSERT into `bid` table with `status=REJECTED` + reason
  6. If `is_proxy`: INSERT into `proxy_bid` table (store-only, no auto-counter in MVP)
- `get_bid_history(db, auction_id, cursor, limit) -> BidHistoryPage`
- `reconstruct_state(redis, auction_id) -> dict` — rebuild Redis hash from PostgreSQL on cold start

Tier: **staff-engineer** — core atomic bid path, dedup, persistence

### `FanOutService` — `src/auction_app/services/fanout_service.py`

Broadcasts bid events to WebSocket watchers via Redis Pub/Sub. Masks bidder
identity in broadcast payloads.

Key methods:
- `publish_bid_accepted(redis, auction_id, bid_result) -> None`
  — PUBLISH `fanout:auction:{id}` with masked payload
- `mask_bidder_id(bidder_id) -> str` — first 8 chars of SHA256 hex
- `get_current_state(redis, auction_id) -> dict` — HGETALL for initial WS frame

Tier: **senior-engineer** — straightforward Pub/Sub + masking

### `SearchService` — `src/auction_app/services/search_service.py`

Full-text search over active auctions using PostgreSQL `tsvector` + GIN index.
Supports category filter, price range, keyword query, cursor pagination.

Key methods:
- `search_auctions(db, category, price_min, price_max, q, state, cursor, limit) -> SearchResult`
  — Build parameterized query with `to_tsquery` for FTS, `WHERE` clauses for filters,
    `ORDER BY created_at DESC`, cursor-based pagination via base64-encoded `(created_at, auction_id)`

Tier: **senior-engineer** — parameterized SQL, no custom index logic

### `SchedulerService` — `src/auction_app/services/scheduler_service.py`

APScheduler-based lifecycle driver. Runs inside the FastAPI lifespan. Polls
PostgreSQL for auctions whose `start_ts` or `end_ts` has been reached and
dispatches `start_auction`/`close_auction` calls.

Key methods:
- `start_scheduler(auction_service) -> None` — register APScheduler jobs
- `poll_due_starts() -> None` — SELECT auctions WHERE state='UPCOMING' AND start_ts <= NOW()
- `poll_due_closes() -> None` — SELECT auctions WHERE state='ACTIVE' AND end_ts <= NOW()

Poll interval: 1 second. Each poll processes up to 100 auctions. Jitter: auction
end_ts already has random jitter applied at creation time (±15 min).

Tier: **senior-engineer** — straightforward APScheduler integration

## Module Layout

```
online-auction-mvp/
├── README.md
├── AGENTS.md               # kanban harness (exists)
├── KICKOFF.md              # kickoff instructions
├── DEPLOY.md               # host run/teardown (to be written by sre)
├── docs/
│   ├── arch.md             # ← this file
│   ├── system-design.md    # full target design (from Notion)
│   └── mvp-scope.md        # scope + build plan
├── .gitignore
├── .env.example
├── pyproject.toml
├── requirements.txt
├── Dockerfile              # multi-stage, python:3.12-slim
├── docker-compose.yml
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_auction_tables.py
├── src/auction_app/
│   ├── __init__.py
│   ├── main.py             # create_app() factory, lifespan (scheduler), /healthz
│   ├── config.py           # pydantic-settings: DATABASE_URL, REDIS_URL, etc.
│   ├── database.py         # async engine/session, get_session dependency
│   ├── redis_client.py     # redis.asyncio connection pool, get_redis dependency
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py             # User ORM model
│   │   ├── auction.py          # Auction ORM model (with tsvector column)
│   │   ├── bid.py              # Bid ORM model
│   │   └── proxy_bid.py        # ProxyBid ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── user.py             # UserCreate, UserResponse
│   │   ├── auction.py          # AuctionCreate, AuctionResponse, AuctionDetail
│   │   ├── bid.py              # BidRequest, BidResponse, BidHistoryPage
│   │   └── search.py           # SearchParams, SearchResult
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── health.py           # GET /healthz
│   │   ├── users.py            # POST /users
│   │   ├── auctions.py         # POST /auctions, GET /auctions/{id}, GET /auctions/{id}/history
│   │   ├── bids.py             # POST /auctions/{id}/bids
│   │   ├── search.py           # GET /auctions (search)
│   │   └── websocket.py        # WS /auctions/{id}/live
│   └── services/
│       ├── __init__.py
│       ├── auction_service.py  # create, start, close, settle
│       ├── bid_service.py      # place_bid (Lua CAS), history, dedup
│       ├── fanout_service.py   # Redis Pub/Sub broadcast + masking
│       ├── search_service.py   # PostgreSQL FTS query builder
│       └── scheduler_service.py # APScheduler lifecycle driver
├── tests/                   # white-box unit/integration tests (import auction_app)
│   ├── conftest.py
│   ├── test_auction_service.py
│   ├── test_bid_service.py
│   ├── test_fanout_service.py
│   └── test_search_service.py
└── verify/
    ├── manifest.env         # e2e-verify contract
    └── acceptance/
        ├── conftest.py                  # httpx client fixture, helpers
        └── test_functional.py           # black-box tests: FR1-FR5 + concurrency
```

## Key Design Decisions

### Decision 1: Redis Lua CAS vs. DB pessimistic locking

**Chosen:** Redis Lua script as the single atomic bid kernel.

**Rejected:** PostgreSQL `SELECT ... FOR UPDATE` or optimistic version-column CAS.

**Rationale:** The full design's DD1 analysis applies directly. At any non-trivial
contention level, pessimistic row locks cause connection pool saturation.
Optimistic locking causes retry storms under high contention (50%+ retry rate at
500 bids/sec). Redis single-threaded execution of the Lua script guarantees
serial order without locks or retries. The durability concern (Redis crash loses
last second of bids) is mitigated by: (a) bids are XADD'd to a Redis Stream
before the CAS, providing an ordered durable log, (b) the `bid_result:{bid_id}`
dedup key prevents double-accept on replay, and (c) accepted bids are immediately
persisted to PostgreSQL.

### Decision 2: Redis Streams vs. Kafka for bid ordering

**Chosen:** Redis Streams (`XADD` / `XREADGROUP`) for MVP.

**Rejected:** Kafka (full design's approach).

**Rationale:** At MVP scale (single-node, no horizontal scaling), Redis Streams
provide ordered, persistent, consumer-group-based message delivery without the
operational overhead of a Kafka cluster. The bid ordering guarantee is maintained
by the Redis single-thread event loop: `XADD` to the stream, then immediately
`EVAL` the CAS script — both happen atomically from the caller's perspective.
Redis Streams support consumer groups and acknowledgement, giving us at-least-once
semantics equivalent to Kafka's for MVP throughput. If the MVP graduates to
production scale, swapping Redis Streams for Kafka is a transport swap — the
service interface stays the same.

### Decision 3: In-process APScheduler vs. external scheduler

**Chosen:** APScheduler running inside the FastAPI lifespan.

**Rejected:** Separate worker process with Redis ZSET + lease-based failover
(full design's approach).

**Rationale:** The full design's distributed scheduler exists because 10M
concurrent auctions with 500K close events per tick require N workers with
lease-based failover. At MVP scale (hundreds to low thousands of auctions), a
single process polling every 1 second handles the close load easily. The auction
end_ts already has jitter applied at creation time, smoothing the scheduler's
poll load. If the process crashes, auctions whose close was missed will be
picked up on restart (the scheduler polls for overdue `ACTIVE` auctions).

### Decision 4: Simplified proxy bidding (store-only)

**Chosen:** Store proxy max bids in `proxy_bid` table; do NOT auto-counter-bid
in MVP.

**Rejected:** Full proxy resolution engine with in-memory sort + single CAS.

**Rationale:** The MVP focuses on the core bid path correctness (atomic CAS,
dedup, anti-snipe). Auto-counter-bidding introduces complexity: the proxy
resolution algorithm must load all active proxies into memory, sort by
`(max_bid DESC, entered_ts ASC)`, and resolve the winner in a single CAS call.
This is the right approach at scale (prevents N× CAS calls for N proxies), but
the MVP's priority is getting the bid kernel right. Storing proxy bids means the
data model is forward-compatible; the resolution engine can be added in a
subsequent phase without a migration.

### Decision 5: Full-text search on PostgreSQL vs. dedicated index

**Chosen:** PostgreSQL `tsvector` generated column + GIN index.

**Rejected:** Elasticsearch or sharded inverted index.

**Rationale:** The full design uses a sharded inverted index because eCommerce
search requires real-time updates and exhaustive recall at 50K+ new listings/day
with millions of concurrent searches. At MVP scale, PostgreSQL FTS with a GIN
index on a `tsvector` generated column provides ranked full-text search, category
filtering, and price range filtering in a single parameterized query — no
separate index pipeline. The `tsvector` column is `GENERATED ALWAYS AS` and
updated automatically on INSERT/UPDATE, so the search index never drifts.

## Tier Assignments (implementation tasks)

| Task | Tier | Reason |
|---|---|---|
| `src/auction_app/main.py` | staff-engineer | App factory, lifespan with scheduler init, health endpoints |
| `src/auction_app/config.py` | staff-engineer | Typed settings with env-driven defaults |
| `src/auction_app/database.py` | staff-engineer | Async session, engine, migration runner |
| `src/auction_app/redis_client.py` | staff-engineer | Async Redis pool, Lua script registration, connection health |
| `src/auction_app/models/*` | staff-engineer | ORM models with correct indexes, tsvector column, constraints |
| `src/auction_app/schemas/*` | senior-engineer | Pydantic request/response DTOs — straightforward validation |
| `src/auction_app/routers/health.py` | senior-engineer | GET /healthz — trivial |
| `src/auction_app/routers/users.py` | senior-engineer | POST /users — simple CRUD |
| `src/auction_app/routers/auctions.py` | senior-engineer | CRUD endpoints — parse, delegate to service |
| `src/auction_app/routers/bids.py` | senior-engineer | Thin router, delegates to BidService |
| `src/auction_app/routers/search.py` | senior-engineer | Query param parsing, delegates to SearchService |
| `src/auction_app/routers/websocket.py` | senior-engineer | WebSocket endpoint, subscription management |
| `src/auction_app/services/auction_service.py` | staff-engineer | Lifecycle transitions, settlement — correctness-critical |
| `src/auction_app/services/bid_service.py` | staff-engineer | Lua CAS execution, dedup, stream + DB persistence — core kernel |
| `src/auction_app/services/fanout_service.py` | senior-engineer | Redis Pub/Sub broadcast, bidder masking |
| `src/auction_app/services/search_service.py` | senior-engineer | Parameterized SQL with FTS — query building |
| `src/auction_app/services/scheduler_service.py` | senior-engineer | APScheduler integration — polling loop |
| `alembic/` migration | staff-engineer | Schema DDL — correctness of constraints, indexes, tsvector |
| `pyproject.toml`, `requirements.txt` | senior-engineer | Dependency declaration |
| `Dockerfile` (multi-stage) | senior-engineer | Python 3.12 slim, venv pattern |
| `docker-compose.yml` | sre | Compose orchestration: db+redis+app, healthchecks, APP_PORT |
| `.env.example`, `.gitignore` | senior-engineer | Configuration docs, hygiene |
| `tests/` (white-box) | senior-engineer | Unit/integration tests for services |
| `verify/manifest.env` | senior-engineer | e2e contract wiring |
| `verify/acceptance/test_functional.py` | senior-engineer | Black-box acceptance suite |
| `README.md`, `DEPLOY.md` | senior-engineer | User-facing docs |
