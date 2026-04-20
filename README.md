# Web App Samples

A collection of self-contained web application designs and reference implementations that demonstrate common backend patterns — relational databases, caches, search engines, message queues, and object storage — with realistic architectural tradeoffs.

The repository is organized in two halves:

- **[`ideas/`](ideas/)** — written specs for eight sample applications, plus a plain-language [concepts](ideas/concepts.md) primer and an [overview](ideas/overview.md) index.
- **[`ecommerce_platform/`](ecommerce_platform/)** — a working full-stack implementation of the first idea (FastAPI + React + Postgres + Valkey + Elasticsearch + MinIO + RabbitMQ).

---

## Repository Layout

```
samples/
├── ideas/                    # App design docs (specs only, no code)
│   ├── overview.md           # Index of all eight ideas + tech reference
│   ├── concepts.md           # Plain-language intro to the building blocks
│   ├── ecommerce_platform.md
│   ├── realtime_chat.md
│   ├── url_shortener.md
│   ├── analytics_dashboard.md
│   ├── restaurant_reservation.md
│   ├── social_feed.md
│   └── job_board.md
└── ecommerce_platform/       # Reference implementation of the first idea
    ├── README.md             # How to run, test, and use Postman
    ├── implementation.md     # Phase-by-phase build log
    ├── docker-compose.yml    # Postgres, Valkey, Elasticsearch, MinIO, RabbitMQ
    ├── app/                  # FastAPI backend
    ├── workers/              # Async order-processing consumer
    ├── frontend/             # React + Vite + TypeScript + Tailwind
    ├── tests/                # 29 pytest cases (unit + E2E)
    ├── migrations/           # Alembic schema migrations
    └── postman_collection.json
```

---

## The Sample Ideas

Each idea in [`ideas/`](ideas/) follows the same shape: an overview, a tech-stack table, a key challenge, and notes on how to scale. They are designed to be implemented independently.

| # | Idea | Highlight Stack | Key Challenge |
|---|---|---|---|
| 1 | [E-Commerce Platform](ideas/ecommerce_platform.md) | Postgres · Redis · Elasticsearch · S3 · RabbitMQ | Preventing oversell during flash sales |
| 2 | [Real-Time Chat](ideas/realtime_chat.md) | MongoDB · Redis Pub/Sub · WebSockets · S3 | Horizontally scaling WebSocket servers |
| 3 | [URL Shortener](ideas/url_shortener.md) | Postgres · Redis · ClickHouse · Kafka | Sub-millisecond redirect latency |
| 4 | [Analytics Dashboard](ideas/analytics_dashboard.md) | Kafka · ClickHouse · Redis · Postgres | Exactly-once Kafka → ClickHouse delivery |
| 5 | [Restaurant Reservation](ideas/restaurant_reservation.md) | Postgres · Redis · Elasticsearch/PostGIS · RabbitMQ | Preventing double-booking |
| 6 | [Social Media Feed](ideas/social_feed.md) | Postgres · Redis · S3 · Elasticsearch · Kafka | Fan-out for celebrity accounts |
| 7 | [Job Board / ATS](ideas/job_board.md) | Postgres · Redis · Elasticsearch · S3 · Sidekiq/BullMQ | Multi-factor search ranking |

See [`ideas/overview.md`](ideas/overview.md) for full tech reference tables and a docker-compose skeleton that covers most of the stacks above.

---

## The Reference Implementation: `ecommerce_platform/`

The first idea is fully implemented as a runnable example.

**Stack**
- **Backend** — FastAPI (async), SQLAlchemy + asyncpg, Alembic
- **Frontend** — React 18, Vite, TypeScript, Tailwind, react-router
- **Storage** — PostgreSQL (orders/inventory), Valkey/Redis (cart + cache + rate limiting), Elasticsearch (search + autocomplete), MinIO (product images), RabbitMQ (post-order tasks)
- **Tests** — 29 pytest cases including a full end-to-end purchase flow

**Quick start**
```bash
cd ecommerce_platform
docker compose up -d              # start all infra
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload     # backend on :8000

# in another terminal
cd frontend && npm install && npm run dev   # frontend on :5173
```

For the complete walkthrough — running, testing, the Postman collection, and the worker — see [`ecommerce_platform/README.md`](ecommerce_platform/README.md). For the build history and design decisions, see [`ecommerce_platform/implementation.md`](ecommerce_platform/implementation.md).

---

## Running Things Locally

Every idea in this repo is designed to run for free on a single laptop using Docker. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (free for personal use) and you have everything you need — no cloud accounts required.

The [overview doc](ideas/overview.md#running-locally-free-no-hosting-required) maps each technology to its local Docker image and explains the cloud-to-local substitutions (S3 → MinIO, SQS → RabbitMQ, etc.).

---

## Suggested Reading Order

1. **[`ideas/concepts.md`](ideas/concepts.md)** if you're new to web-app architecture.
2. **[`ideas/overview.md`](ideas/overview.md)** for the big-picture comparison of all eight ideas.
3. Pick an idea that interests you and read its dedicated file in `ideas/`.
4. **[`ecommerce_platform/`](ecommerce_platform/)** to see one of these designs translated into working code, tests, and documentation.

---

## Contributing New Samples

To add another sample idea, create a new markdown file in `ideas/` following the existing structure (Overview → Stack table → Key challenge → Scaling notes) and link it from `ideas/overview.md`. To add another reference implementation, mirror the layout of `ecommerce_platform/` (its own README, docker-compose, tests, and an `implementation.md` build log).
