# Implementation Guide — E-Commerce Platform

This document explains what was built, why each decision was made, and how to test each component. Follow along phase by phase.

---

## Technology Choices

### Why Valkey instead of Redis?

In March 2024, Redis Ltd. changed Redis from the BSD open-source license to the
Server Side Public License (SSPL). SSPL restricts how companies can offer Redis as
a managed service. In response, the Linux Foundation created **Valkey** — a
community-maintained fork of Redis under the original BSD license.

From an application code perspective, nothing changes:
- Valkey uses the identical wire protocol as Redis
- All Redis commands work unchanged
- The `redis-py` Python client connects to Valkey without modification
- Hosted Valkey services (AWS ElastiCache for Valkey, Upstash) are drop-in replacements

The only practical differences are the Docker image name (`valkey/valkey` instead of `redis`) and
the CLI binary (`valkey-cli` instead of `redis-cli`).

### Local vs. hosted services

Every service in this app has a Docker-based local version and a cloud-hosted production equivalent.
The application code never hard-codes which one to use — it reads connection details from environment
variables. Switching environments is purely a configuration change.

| Service | Local (Docker) | Hosted option | Config variable |
|---|---|---|---|
| PostgreSQL | `postgres:16` | AWS RDS, Supabase, Neon | `POSTGRES_URL` |
| Valkey | `valkey/valkey:8` | AWS ElastiCache, Upstash | `REDIS_URL` |
| Elasticsearch | `elasticsearch:8.13.0` | Elastic Cloud, AWS OpenSearch | `ELASTICSEARCH_URL` |
| Object storage | `minio/minio` | AWS S3, Cloudflare R2 | `STORAGE_ENDPOINT_URL` + credentials |
| Message queue | `rabbitmq:3-management` | CloudAMQP, AWS MQ | `RABBITMQ_URL` |

See `.env.example` for full connection string examples for each hosted option.

---

## Phase 1 — Foundation & Docker Compose

**Goal:** Get all services running locally and the FastAPI app connected to each.

### What we built
- `docker-compose.yml` — spins up all five services with one command
- `app/config.py` — reads connection strings from environment variables; defaults to local Docker values
- `app/main.py` — FastAPI app that connects to every service on startup via a `lifespan` handler
- `app/database.py`, `cache.py`, `search.py`, `storage.py`, `queue.py` — thin connection modules, one per service
- `migrations/init.sql` — creates all tables; auto-runs when the postgres container first starts

### How the lifespan pattern works
FastAPI's `lifespan` replaces the old `@app.on_event("startup")`. It runs setup code before the app accepts requests and teardown code after it stops. This ensures connections are opened once and closed cleanly:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_redis()           # connect to Valkey
    await ensure_products_index()
    yield                       # app runs here
    await close_redis()         # disconnect
```

### How to test Phase 1
```bash
docker compose up -d
uvicorn app.main:app --reload
curl localhost:8000/health
# Expected: {"redis":"ok","postgres":"ok","elasticsearch":"ok"}
```

If a service shows `"error: ..."`, wait a few more seconds and retry — Elasticsearch is slow to start.

---

## Phase 2 — Product Catalog

**Goal:** Create products stored in PostgreSQL, cached in Redis, and indexed in Elasticsearch.

### What we built
- `app/models/product.py` — SQLAlchemy ORM model mapping to the `products` table
- `app/schemas/product.py` — Pydantic models for request validation and response serialization
- `app/routers/products.py` — CRUD endpoints + search + autocomplete + image upload

### Cache-aside pattern (Redis)

When a product is fetched:
1. Check Redis for `product:{id}`
2. If found (cache hit): return immediately — no database query at all
3. If not found (cache miss): query PostgreSQL, write result to Redis with a 60-second TTL, return

```
GET /products/42
      │
      ├─► Redis GET product:42 ──► HIT  ──► return cached JSON (< 1ms)
      │
      └─► MISS ──► PostgreSQL SELECT * FROM products WHERE id=42
                       │
                       └─► Redis SET product:42 <json> EX 60
                               │
                               └─► return to client
```

**Cache invalidation:** When a product is updated via `PUT /products/{id}`, the cache entry is deleted immediately with `redis.delete(key)`. The next `GET` will repopulate it from PostgreSQL with fresh data.

### Why Elasticsearch instead of `LIKE '%query%'`?

A PostgreSQL query like `WHERE name LIKE '%boots%'` scans every row in the products table. As the catalog grows, this becomes slow. Elasticsearch builds an **inverted index**: a map from each word to the documents containing it. "boots" → [product 1, product 7, product 23]. Lookups are O(1) regardless of catalog size.

Elasticsearch also scores results by relevance (how many times does the search term appear? how important is the field?), whereas a `LIKE` match returns all rows with equal weight.

### How to test Phase 2
```bash
# Create a product
curl -X POST localhost:8000/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Waterproof Jacket","category":"clothing","price":199.99,"stock":20}'

# Fetch it (first time = cache miss, second time = cache hit)
curl localhost:8000/products/1
curl localhost:8000/products/1

# Search
curl "localhost:8000/products/search?q=jacket"
curl "localhost:8000/products/search?q=jacket&max_price=150"

# Autocomplete
curl "localhost:8000/products/search/autocomplete?q=water"
```

---

## Phase 3 — Cart & Sessions (Valkey)

**Goal:** Shopping cart backed entirely by Redis, with automatic expiry.

### What we built
- `app/routers/cart.py` — add/remove/view/clear cart endpoints + rate limiting middleware

### Why the cart lives in Valkey, not PostgreSQL

A shopping cart is **ephemeral** — if someone abandons it, it should disappear. Storing it in PostgreSQL would require:
- A background job to delete abandoned carts
- Writing to the database on every item add/remove (slow)
- More complex queries to read cart + product details

Redis handles this better:
- The cart is a **Redis hash**: key = `cart:{session_id}`, fields = product IDs, values = quantities
- TTL is set on the key — it auto-deletes after 24 hours of inactivity, no cleanup job needed
- Reads and writes are sub-millisecond

```
Redis Hash: cart:abc123
  ┌─────────────┬──────────┐
  │ Field       │ Value    │
  ├─────────────┼──────────┤
  │ "1"         │ "2"      │  ← product_id=1, quantity=2
  │ "7"         │ "1"      │  ← product_id=7, quantity=1
  └─────────────┴──────────┘
  TTL: 86400 seconds (24h)
```

### Rate limiting

Each request to the cart API increments a Redis counter keyed by IP:
```
INCR rate:192.168.1.1
EXPIRE rate:192.168.1.1 60   (set on first increment only)
```
If the counter exceeds 100, the request returns HTTP 429. The key expires automatically after 60 seconds, resetting the limit — no cron job needed.

### How to test Phase 3
```bash
# Add items
curl -X POST localhost:8000/cart/my-session/items \
  -H "Content-Type: application/json" \
  -d '{"product_id":1,"quantity":2}'

# View cart
curl localhost:8000/cart/my-session

# Remove one item
curl -X DELETE localhost:8000/cart/my-session/items/1

# Clear cart
curl -X DELETE localhost:8000/cart/my-session
```

---

## Phase 4 — Checkout & Orders (PostgreSQL ACID)

**Goal:** Atomic checkout that prevents overselling and preserves data integrity.

### What we built
- `app/models/order.py` — Order and OrderItem ORM models
- `app/schemas/order.py` — CheckoutRequest, OrderResponse Pydantic models
- `app/routers/orders.py` — `/orders/checkout` and `/orders/{id}`

### The oversell problem

Imagine two customers trying to buy the last item simultaneously:

```
Time  Customer A                Customer B
  0   Read stock = 1            Read stock = 1
  1   Check: 1 >= 1 ✓          Check: 1 >= 1 ✓
  2   stock = stock - 1 = 0    stock = stock - 1 = 0  ← both succeed!
  3   Create order A            Create order B
```

Both see stock = 1, both pass the check, both create orders. The item is sold twice.

### The fix: `SELECT FOR UPDATE`

`SELECT FOR UPDATE` locks the row for the duration of the transaction. The second request cannot read the row until the first commits:

```
Time  Customer A                    Customer B
  0   SELECT ... FOR UPDATE         SELECT ... FOR UPDATE
  1   → gets the lock               → WAITS (blocked on lock)
  2   Check: 1 >= 1 ✓
  3   stock = 0, create order A
  4   COMMIT → releases lock        → gets the lock, reads stock = 0
  5                                 Check: 0 >= 1 ✗ → 409 error
```

### Why publish to the queue AFTER the commit

If we published to RabbitMQ before committing the database transaction, and then the transaction rolled back (due to a crash or constraint violation), the worker would process an order that never landed in the database. Always commit first, then publish.

### How to test Phase 4
```bash
# Add to cart first
curl -X POST localhost:8000/cart/my-session/items \
  -H "Content-Type: application/json" \
  -d '{"product_id":1,"quantity":2}'

# Checkout
curl -X POST localhost:8000/orders/checkout \
  -H "Content-Type: application/json" \
  -d '{"session_id":"my-session","user_id":1}'

# View order
curl localhost:8000/orders/1
```

---

## Phase 5 — Background Workers (RabbitMQ)

**Goal:** Process post-order tasks asynchronously in a separate process.

### What we built
- `app/queue.py` — aio-pika connection; `publish()` helper used by the checkout endpoint
- `workers/order_worker.py` — standalone consumer process

### How it works

1. `POST /orders/checkout` commits the order to PostgreSQL
2. It publishes `{"event": "order.created", "order_id": 7, "user_id": 1, "total": 99.98}` to the `orders` queue in RabbitMQ
3. The checkout endpoint immediately returns the order to the customer
4. Separately, `order_worker.py` (running as its own process) reads from the queue and handles:
   - Sending a confirmation email (currently logged to console)
   - Notifying the warehouse system (currently logged to console)

This is why checkout feels instant to the customer even though emails and warehouse notifications take time — they happen asynchronously.

### At-least-once delivery

RabbitMQ guarantees a message is delivered at least once. If the worker crashes mid-processing, RabbitMQ re-delivers the message to another worker. This means handlers should be **idempotent** — processing the same order twice should not send two emails. In production you'd record processed order IDs in a database and skip duplicates.

### How to test Phase 5
In a second terminal:
```bash
python -m workers.order_worker
```

Then place an order in the first terminal and watch the worker logs:
```
[EMAIL] Sending confirmation to user 1 — order #3, total $179.97
[WAREHOUSE] Notifying fulfillment for order #3
```

---

## Phase 6 — Object Storage (MinIO / S3)

**Goal:** Store and serve product images without using the database.

### What we built
- `app/storage.py` — boto3 S3 client; points to MinIO locally, real S3 in production
- `POST /products/{id}/image` — upload endpoint
- `GET /products/{id}/image-url` — pre-signed URL generation

### Why not store images in PostgreSQL?

Storing binary files in a database column (`BYTEA` in PostgreSQL) causes several problems:
- Database backups become enormous
- Every image fetch goes through the database connection pool (limited resource)
- No built-in CDN support
- Database CPU and I/O are consumed by file serving instead of query processing

Object storage (MinIO/S3) is designed for exactly this — cheap, durable, scalable, and serves files via HTTP directly without involving the app server.

### Pre-signed URLs

Rather than proxying file downloads through the API, we generate a **pre-signed URL** — a URL that includes a cryptographic signature granting temporary read access:

```
https://localhost:9000/product-images/products/7/photo.jpg?X-Amz-Signature=abc&X-Amz-Expires=3600
```

The URL expires after 1 hour. If leaked, it can't be used indefinitely. The API server never touches the file bytes during download — the client fetches directly from MinIO/S3.

### Local vs. production: one config change

```python
# Local (MinIO)
STORAGE_ENDPOINT_URL=http://localhost:9000

# Production (AWS S3) — just remove STORAGE_ENDPOINT_URL
# boto3 automatically uses S3 when no endpoint is specified
```

### How to test Phase 6
```bash
# Upload an image (use any small file)
curl -X POST localhost:8000/products/1/image \
  -F "file=@/path/to/photo.jpg"

# Get a pre-signed download URL
curl localhost:8000/products/1/image-url

# Copy the URL from the response and open it in a browser or curl it
```

---

## Running All Tests

```bash
# Make sure docker compose is running
pytest tests/ -v
```

### What the tests cover

| Test file | What it verifies |
|---|---|
| `test_products.py` | Create, fetch, cache miss→hit cycle, cache invalidation on update, search with filters |
| `test_cart.py` | Add items, view cart, remove items, empty cart, TTL set after add |
| `test_checkout.py` | Happy path, insufficient stock (409), empty cart (400), cart cleared after checkout, concurrent oversell prevention |

### The concurrent oversell test

`test_oversell_prevention_concurrent` in `test_checkout.py` fires two checkout requests simultaneously using `asyncio.gather`. Both try to buy the last unit. The test asserts exactly one HTTP 201 and one non-201 response — proving `SELECT FOR UPDATE` prevented the oversell.

---

## Phase 7 — Frontend (React + Vite + TypeScript + Tailwind)

**Goal:** Provide a real browser UI in front of the backend so the same flows you tested with `curl` (search, add to cart, checkout, image upload) can be exercised end-to-end visually.

### What we built

```
frontend/
├── index.html              # single mount point
├── vite.config.ts          # /api → http://localhost:8000 proxy
├── tailwind.config.js      # custom slide-in / fade-in animations
├── src/
│   ├── main.tsx            # mounts <App/> in <BrowserRouter>
│   ├── App.tsx             # provider stack + <Routes>
│   ├── index.css           # Tailwind base/components/utilities
│   ├── api/client.ts       # one typed function per backend endpoint
│   ├── types/index.ts      # interfaces mirroring the Pydantic schemas
│   ├── context/
│   │   ├── CartContext.tsx     # session id (uuid in localStorage), cart, drawer state
│   │   └── UserContext.tsx     # currently signed-in user (localStorage)
│   ├── components/
│   │   ├── Navbar.tsx          # logo + autocomplete search + cart badge + user menu
│   │   ├── CartDrawer.tsx      # slide-over cart panel
│   │   ├── ProductCard.tsx     # grid card used on the home page
│   │   ├── Toast.tsx           # ephemeral bottom-right notifications
│   │   └── LoadingSpinner.tsx  # centered spinner
│   └── pages/
│       ├── HomePage.tsx        # search results, URL-driven filters
│       ├── ProductPage.tsx     # detail view + qty selector
│       ├── CheckoutPage.tsx    # sign-in + place order + confirmation
│       ├── AdminPage.tsx       # create products, upload images, edit price/stock
│       └── HealthPage.tsx      # backing-service status pills
```

### How requests reach the backend (Vite proxy)

The frontend never hard-codes `http://localhost:8000`. Every API call goes to the relative path `/api/*`. Vite's dev server forwards those requests to the FastAPI backend with the `/api` prefix stripped:

```
Browser                Vite dev server (5173)         FastAPI (8000)
   │                            │                            │
   │ fetch("/api/products/1")   │                            │
   │ ─────────────────────────► │ GET /products/1            │
   │                            │ ─────────────────────────► │
   │                            │ ◄───────────────────────── │
   │ ◄───────────────────────── │   200 { ... product ... }  │
```

This means:

- No CORS configuration needed during development — both ports look like the same origin to the browser.
- The same code works in production by serving the static build from any host that proxies `/api/*` to the backend (or by setting `BASE` to a full URL in `api/client.ts`).

### State management — minimal, intentional

We use plain React **context** + **`useState`**/`useEffect` rather than a data-fetching library (SWR, React Query, Redux, etc.):

- **`CartContext`** owns the browser's session id (a UUID generated on first visit, persisted to `localStorage`) and the latest cart returned by the backend. Every screen that reads or modifies the cart goes through `useCart()`.
- **`UserContext`** owns the signed-in user, also persisted to `localStorage`. The backend has no email-based lookup endpoint, so "sign in" is a one-shot `POST /users` (with a fallback that asks for a numeric user id if the email is taken). A real app would replace this with proper authentication.
- **`ToastProvider`** is a tiny notification system used across the app (`addToast("Added to cart", "success")`).

The result is short, readable components and zero hidden caching — the cache-aside pattern lives entirely on the backend (Valkey), where it belongs.

### Architectural notes worth highlighting

- **The Redis cache is invisible to the frontend.** The first product fetch hits PostgreSQL, the second hits Valkey, but `getProduct(id)` looks identical in both cases. This is the whole point of a server-side cache.
- **The home page is URL-driven.** Search query, category, and price filters live in the query string (`/?q=boots&category=footwear&max_price=200`) so users can bookmark, share, or refresh searches without losing state.
- **Autocomplete is debounced by 200 ms** in `Navbar.tsx` — typing fast still produces only one Elasticsearch suggester request per pause, not one per keystroke.
- **Product images are served via pre-signed URLs.** The frontend asks the backend for `/api/products/:id/image-url`, then puts the returned URL straight into an `<img src=...>` — the bytes flow directly from MinIO/S3 to the browser, never through the API server.
- **Checkout reflects ACID guarantees in the UI.** A 409 "Insufficient stock" from the backend (when `SELECT FOR UPDATE` blocks a conflicting checkout) becomes a red toast; the cart is not cleared and the user can retry.

### How to test Phase 7

```bash
# 1. Backend services + API running (see Phase 1)
cd ecommerce_platform
docker compose up -d
uvicorn app.main:app --reload

# 2. In a second terminal, start the frontend
cd ecommerce_platform/frontend
npm install
npm run dev
# → http://localhost:5173

# 3. End-to-end smoke test in the browser
#    - Visit /admin and create 2-3 products (try uploading an image)
#    - Visit / and confirm they appear; type in the search box for autocomplete
#    - Click a product → ProductPage → "Add to Cart" → drawer slides in
#    - Click "Checkout →" → enter email + name → "Place order" → confirmation
#    - Visit /health to confirm all three services are green
```

### Production build

```bash
cd ecommerce_platform/frontend
npm run build       # runs `tsc && vite build`
npm run preview     # serves dist/ on http://localhost:4173
```

The static `dist/` bundle can be deployed to any static host (S3 + CloudFront, Netlify, Vercel, Cloudflare Pages). Configure the host to forward `/api/*` to the FastAPI backend (or change `BASE` in `src/api/client.ts` to a full URL).
