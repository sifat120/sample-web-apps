# URL Shortener Service

> **New to web apps?** Read [concepts.md](concepts.md) first — it explains databases, caches, message queues, and other building blocks used throughout this document.

## Overview
A service that maps a short code (e.g., `short.ly/x7kq`) to a long URL (e.g., `https://www.example.com/very/long/path?with=many&query=params`). When someone visits the short URL, they are instantly redirected to the original. Services like bit.ly, TinyURL, and t.co (Twitter) work this way.

This app is a great case study in **caching**, because redirects are read millions of times but the underlying data barely changes. The goal is to answer a redirect in under a millisecond.

## Key Features
- Shorten any URL to a compact code
- Redirect short codes to original URLs
- Click analytics: count, referrer, geography, device type
- Custom aliases and expiration dates
- API access with per-key rate limiting

---

## Infrastructure

### Primary Database — PostgreSQL
**What it is:** A relational database that stores structured data in tables. See [Relational Databases](concepts.md#3-relational-databases-sql).

**Why it's used here:** The core data (short code → long URL mapping) is perfectly structured and relational. PostgreSQL is reliable and its ACID guarantees mean a URL mapping, once saved, is never lost.

**What it stores:**
- `urls` table: each row is one shortened URL
  - `short_code` — the 6-8 character code (e.g., `x7kq`)
  - `long_url` — the original destination URL
  - `owner_id` — which user created this short link
  - `created_at` — when it was created
  - `expires_at` — optional expiration date (after which the link stops working)
  - `is_active` — whether the link is currently enabled
- `clicks` table: each row records one redirect event (for analytics)

---

### Cache — Redis
**What it is:** An in-memory store that serves data much faster than a database. See [The Cache](concepts.md#5-the-cache).

**Why it's the most important piece here:** Almost every request to a URL shortener is a redirect — someone visiting a short link. These reads vastly outnumber writes (new links being created). If we can serve redirects from Redis instead of hitting PostgreSQL every time, we can handle massive traffic at extremely low latency.

**How it's used:**

- **Redirect cache**: The mapping `short_code → long_url` is stored in Redis. Nearly every redirect request finds its answer here (a cache hit) without ever touching PostgreSQL. The TTL on each entry matches the link's expiration date, so expired links fall out of the cache automatically. See [TTL](concepts.md#14-ttl-time-to-live).

- **Short code generation**: Every new shortened URL needs a unique ID. Redis has an `INCR` command that atomically increments a global counter (e.g., `1 → 2 → 3 → ...`). That number is then encoded in base-62 (using digits 0-9 and letters a-zA-Z) to produce a short code like `x7kq`. Because `INCR` is atomic, two simultaneous requests can never get the same number, guaranteeing no collisions.

- **Rate limiting**: Each API key is allowed a certain number of requests per minute. Redis counters track usage per key and reject requests that exceed the limit. See [Rate Limiting](concepts.md#12-rate-limiting).

---

### Analytics Database — ClickHouse (optional)
**What it is:** A columnar database optimized for running aggregation queries over very large datasets quickly.

**Why it's used here:** The `clicks` table could grow to hundreds of millions of rows. Running a query like "how many clicks did all my links get per day this month, broken down by country?" against PostgreSQL would be very slow at that scale. ClickHouse is designed for exactly this kind of analytical query — it reads only the columns it needs and processes them with highly optimized routines.

**Columnar vs. row-based storage explained:**
- A regular (row-based) database stores all fields of a row together: `[click_id, url_id, timestamp, country, referrer, device]`
- A columnar database stores each column separately: all timestamps together, all countries together, etc.
- If your query only needs `timestamp` and `country`, columnar storage reads a tiny fraction of the data — much faster.

---

### Message Queue — Kafka (local) / SQS (managed cloud) (optional)
**What it is:** A buffer for async background tasks. See [The Message Queue](concepts.md#6-the-message-queue).

**Why it's used here:** Recording a click in the analytics database is not critical to the redirect itself — the user doesn't need to wait for it. The redirect handler publishes a lightweight click event to the queue and immediately issues the redirect response. A background consumer reads events from the queue and batch-inserts them into ClickHouse. This keeps redirect latency as low as possible. See [Async Processing](concepts.md#15-async-processing-and-background-jobs).

---

## Data Flow

**Creating a short link:**
1. User submits a long URL via the API
2. Server calls Redis `INCR` to get a unique number → converts to base-62 short code
3. Mapping saved to PostgreSQL (permanent record)
4. Mapping also stored in Redis cache with the appropriate TTL

**Redirecting a short link:**
1. User visits `short.ly/x7kq`
2. Server checks Redis for `x7kq` → cache hit: send HTTP redirect to the long URL immediately (< 1ms)
3. If cache miss: query PostgreSQL → populate Redis cache → send redirect
4. Server publishes a click event to the queue (asynchronously, doesn't delay the redirect)
5. Analytics consumer reads the event and writes it to ClickHouse in a micro-batch

---

## Interesting Engineering Challenges

- **Globally unique short codes without a bottleneck**: Using a single Redis counter works well for one server, but if the counter server goes down, all new link creation stops. Production systems use distributed ID generation strategies to eliminate this single point of failure.
- **Cache stampede**: If a viral URL's cache entry expires, thousands of requests might hit the database simultaneously at the exact same moment before any of them can repopulate the cache. The fix is to use a lock so only one request fetches from the database while the rest wait.
- **Sub-millisecond redirect latency**: The entire redirect path — receive request, check Redis, send HTTP 301 response — should complete in under 1 millisecond for cached entries. This is achievable because Redis reads from memory and the network round-trip to a local Redis instance is tiny.
