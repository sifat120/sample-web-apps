# E-Commerce Platform — Sample App

A sample e-commerce application demonstrating how real online storefronts are built, using:

| Service | Local (Docker) | Hosted (production) | What it does |
|---|---|---|---|
| Primary database | PostgreSQL | AWS RDS, Cloud SQL, Supabase | Products, orders, users — ACID transactions |
| Cache | Valkey | AWS ElastiCache (Valkey), Upstash | Product page cache, shopping carts, rate limiting |
| Search | Elasticsearch | Elastic Cloud, AWS OpenSearch | Full-text product search, autocomplete |
| Object storage | MinIO | AWS S3, Cloudflare R2 | Product images |
| Message queue | RabbitMQ | CloudAMQP, AWS MQ | Async post-order tasks |

Backend: **Python + FastAPI**. Frontend: **React + Vite + TypeScript + Tailwind**.

> **Why Valkey instead of Redis?**
> Redis changed to a non-open-source license (SSPL) in 2024. Valkey is a community fork
> maintained by the Linux Foundation under the BSD license. It is 100% protocol-compatible —
> all Redis clients and hosted services work without code changes.

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (free for personal use)
- Python 3.11+ and `pip` (for the backend)
- Node.js 18+ and `npm` (for the frontend)

---

## Quick Start (Local)

**1. Start all backing services**
```bash
cd ecommerce_platform
docker compose up -d
```

Wait ~30 seconds for Elasticsearch to finish initializing. Check all services are healthy:
```bash
docker compose ps
```
All five services should show `(healthy)` in the STATUS column.

**2. Create and activate a virtual environment**
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
```

**3. Install Python dependencies**
```bash
pip install -r requirements.txt
```

**4. Copy the environment file**
```bash
cp .env.example .env
```
The defaults in `.env.example` match the Docker Compose services — no changes needed for local development.

**5. Start the API**
```bash
uvicorn app.main:app --reload
```

The API is now running at `http://localhost:8000`.

**6. Verify all services are connected**
```bash
curl localhost:8000/health
```
Expected: `{"redis":"ok","postgres":"ok","elasticsearch":"ok"}`

---

## Interactive API Docs

FastAPI generates documentation automatically from the code:
- **Swagger UI** (try endpoints in the browser): http://localhost:8000/docs
- **ReDoc** (clean reference): http://localhost:8000/redoc

---

## Running the Frontend (React)

The frontend lives in `frontend/` and talks to the FastAPI backend via a Vite
dev-server proxy (any request to `/api/*` is forwarded to `http://localhost:8000`,
so there are no CORS problems in development).

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 in your browser. The app provides:

| Route | What it does |
|---|---|
| `/` | Product catalog with search, autocomplete, category & price filters |
| `/products/:id` | Product detail page with image, stock, and add-to-cart |
| `/checkout` | Lightweight sign-in (creates a user) and order placement |
| `/admin` | Create products, upload images, edit price/stock |
| `/health` | Live status of PostgreSQL, Valkey, and Elasticsearch |

Production build:

```bash
cd frontend
npm run build      # type-checks (tsc) and emits dist/
npm run preview    # serves the built bundle locally
```

See `implementation.md` (Phase 7) for an architectural walkthrough.

---

## Manual Testing (curl)

```bash
# Create a user
curl -X POST localhost:8000/users \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@example.com","name":"Alice"}'

# Create a product
curl -X POST localhost:8000/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Trail Shoes","description":"Lightweight trail runners","category":"footwear","price":119.99,"stock":25}'

# Search products
curl "localhost:8000/products/search?q=trail"

# View a product (first fetch = cache miss; second = served from Valkey cache)
curl localhost:8000/products/1
curl localhost:8000/products/1

# Add to cart
curl -X POST localhost:8000/cart/my-session/items \
  -H "Content-Type: application/json" \
  -d '{"product_id":1,"quantity":2}'

# View cart
curl localhost:8000/cart/my-session

# Checkout
curl -X POST localhost:8000/orders/checkout \
  -H "Content-Type: application/json" \
  -d '{"session_id":"my-session","user_id":1}'
```

---

## Running the Background Worker

The order worker runs as a **separate process** from the API. Open a second terminal:

```bash
source .venv/bin/activate
python -m workers.order_worker
```

After placing an order you will see the worker print:
```
[EMAIL] Sending order confirmation to user 1 — order #1, total $239.98
[WAREHOUSE] Notifying fulfillment team for order #1
```

---

## Running Tests

The repository ships with **29 automated tests** that exercise every backing service against the real local Docker stack — not mocks.

### One-time setup

```bash
cd ecommerce_platform

# 1. Backing services must be running
docker compose up -d
docker compose ps      # all five rows must show (healthy)

# 2. Python deps (skip if already done)
source .venv/bin/activate
pip install -r requirements.txt
```

### Run everything

```bash
pytest tests/ -v
# → 29 passed in ~2s
```

### Run a subset

```bash
pytest tests/test_e2e_purchase.py -v          # full end-to-end purchase flow
pytest tests/ -v -k "cache or cart"           # any test whose name matches
pytest tests/test_storage_and_images.py -v    # MinIO/S3 image roundtrip only
```

### What each test file covers

| File | What it verifies |
|---|---|
| `test_health.py` | `/health` returns `ok` for postgres, valkey, elasticsearch |
| `test_users.py` | createUser 201, duplicate-email 409, getUser, 404 |
| `test_products.py` | create, cache miss → hit cycle, cache invalidation on update, search + price filter, 404 |
| `test_autocomplete.py` | Elasticsearch completion suggester returns newly-indexed names |
| `test_storage_and_images.py` | upload bytes → presigned URL → re-download proves bytes match; 404 paths |
| `test_cart.py` | add/remove/clear, TTL is set on the cart hash, invalid product 404 |
| `test_checkout.py` | happy path, insufficient stock 409, empty cart 400, cart cleared, **concurrent oversell prevention** |
| `test_queue_publish.py` | checkout publishes the expected `order.created` message to RabbitMQ |
| `test_e2e_purchase.py` | one test exercises the **whole stack** in 10 explicit steps (PostgreSQL + Elasticsearch + MinIO + Valkey + RabbitMQ) |

> Tests use unique UUID-based emails and cart session ids, so they are safe to re-run repeatedly without resetting the database.

---

## API Testing with Postman

Three options, in order of convenience:

### Option 1 — Import the included collection (recommended)

The repo includes a ready-to-use Postman collection: [`postman_collection.json`](postman_collection.json).

1. Open Postman → **File → Import → Upload Files** → pick `ecommerce_platform/postman_collection.json`.
2. Make sure your backend is running (`uvicorn app.main:app --reload`).
3. The collection defines a `baseUrl` variable that defaults to `http://localhost:8000` — change it in the collection's **Variables** tab if you've deployed the API elsewhere.

The collection is wired to be used **top-to-bottom**:

| Order | Request | What happens automatically |
|---|---|---|
| 1 | Health → GET /health | sanity check |
| 2 | Users → POST /users | response `id` is captured into `{{userId}}` |
| 3 | Products → POST /products | response `id` is captured into `{{productId}}` |
| 4 | Products → POST /products/{id}/image | optional; pick any image file |
| 5 | Products → GET /products/{id} | run twice to see cache miss → cache hit |
| 6 | Cart → POST /cart/{sessionId}/items | uses `{{productId}}` from step 3 |
| 7 | Cart → GET /cart/{sessionId} | shows the line item + total |
| 8 | Orders → POST /orders/checkout | uses `{{sessionId}}` + `{{userId}}`; captures `{{orderId}}` |
| 9 | Orders → GET /orders/{id} | confirms the order persisted |

Variables flow between requests via the collection's test scripts, so you don't have to copy IDs by hand.

You can also run the whole collection at once via **Collection Runner** (▶ icon) for a quick smoke test of every endpoint.

### Option 2 — Import directly from the OpenAPI spec

FastAPI auto-generates an OpenAPI 3 schema. With the backend running:

1. Postman → **File → Import → Link** → paste `http://localhost:8000/openapi.json`.
2. Postman builds a collection with every endpoint, request body schema, and response model populated from the Pydantic models — useful when you've added new endpoints and want an up-to-date collection without editing the JSON file.

### Option 3 — Use the built-in Swagger UI (no Postman needed)

If you don't want to leave the browser, FastAPI's interactive docs let you fire off any request and inspect responses:

- **Swagger UI** — http://localhost:8000/docs
- **ReDoc** (read-only reference) — http://localhost:8000/redoc

---

## Stopping Everything

```bash
# Stop the API with Ctrl+C, then stop Docker services:
docker compose down

# To also delete stored data (database rows, uploaded files):
docker compose down -v
```

---

## Deploying to Production

Switch from local Docker services to hosted cloud services by changing environment variables.
**No code changes are required.** See `.env.example` for full connection string examples.

| Variable | Local default | Hosted example |
|---|---|---|
| `POSTGRES_URL` | Docker PostgreSQL | AWS RDS, Cloud SQL, Supabase, Neon |
| `REDIS_URL` | Docker Valkey | AWS ElastiCache (Valkey), Upstash |
| `ELASTICSEARCH_URL` | Docker Elasticsearch | Elastic Cloud, AWS OpenSearch |
| `STORAGE_ENDPOINT_URL` | `http://localhost:9000` (MinIO) | Remove this var — boto3 auto-targets AWS S3 |
| `STORAGE_ACCESS_KEY` | `minioadmin` | AWS IAM access key |
| `STORAGE_SECRET_KEY` | `minioadmin` | AWS IAM secret key |
| `STORAGE_BUCKET` | `product-images` | Your production bucket name |
| `RABBITMQ_URL` | Docker RabbitMQ | CloudAMQP, AWS MQ |
| `APP_ENV` | `local` | `production` |
| `SECRET_KEY` | `change-me-in-production` | A strong random 64-char hex string |

> **Generating a secure SECRET_KEY:**
> ```bash
> python -c "import secrets; print(secrets.token_hex(32))"
> ```

See [implementation.md](implementation.md) for a detailed walkthrough of every component and
the reasoning behind each technology choice.
