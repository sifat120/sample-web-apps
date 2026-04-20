# Analytics Dashboard

> **New to web apps?** Read [concepts.md](concepts.md) first — it explains databases, caches, message queues, and other building blocks used throughout this document.

## Overview
A SaaS (Software-as-a-Service) platform where businesses embed a small JavaScript snippet into their website to automatically track user behavior — page views, button clicks, purchases, sign-ups. The business can then log into a dashboard to see real-time visitor counts and historical charts.

Think of it as building a simplified version of Google Analytics that companies can embed in their own products.

The two hardest problems here are **ingestion** (accepting millions of tiny events per second without dropping any) and **aggregation** (answering "how many total page views did we get in January?" over billions of stored events in seconds).

## Key Features
- Event ingestion via lightweight JS SDK
- Real-time visitor count and live event stream
- Historical charts: sessions, funnels, retention, top pages
- Custom event tracking and user segmentation
- Exportable reports

---

## Infrastructure

### Event Stream — Apache Kafka
**What it is:** A distributed, high-throughput message streaming system. See [The Message Queue](concepts.md#6-the-message-queue).

**Why it's used instead of writing directly to a database:** The ingestion API receives millions of events per second. Writing each one directly to a database would overwhelm it. Kafka acts as a high-capacity buffer between the API and the database:

- The API publishes each event to Kafka in microseconds and returns immediately
- Kafka durably stores all events on disk (they can be replayed if needed)
- Downstream consumers read from Kafka at their own pace and write to the database in efficient batches

This also means multiple systems can independently consume the same stream of events — the analytics database, a real-time counter service, and an alerting system can all read the same Kafka topic without interfering with each other.

---

### Time-Series Database — ClickHouse
**What it is:** A columnar database built for running fast aggregation queries over enormous datasets.

**Why not PostgreSQL?** PostgreSQL is excellent for typical web app data (users, accounts, settings). But analytics data is different: you might have 50 billion events and want to answer "how many unique users visited the pricing page in March, broken down by country?" PostgreSQL would struggle with this at scale. ClickHouse is engineered specifically for these queries.

**Why columnar storage helps:** A regular database stores all fields of a row together. A columnar database stores each column separately. If your query only needs the `timestamp` and `country` columns out of 20 total columns, columnar storage reads roughly 1/10th of the data — dramatically faster.

**What it stores:**
- `events` table — one row per event:
  - `site_id` — which customer's site this event came from
  - `event_type` — e.g., `page_view`, `button_click`, `purchase`
  - `user_id` — the visitor (may be anonymous)
  - `session_id` — groups events into a single browsing session
  - `timestamp` — when the event occurred
  - `properties` — a JSON blob with arbitrary extra data (page URL, button label, etc.)

---

### Cache — Redis
**What it is:** A fast in-memory store used here for both real-time counters and dashboard query caching. See [The Cache](concepts.md#5-the-cache).

**How it's used:**

- **Real-time visitor count**: When a visitor loads a page, an event fires. The server increments a Redis counter for that site. A sliding window (e.g., "events in the last 5 minutes") shows current active visitors. This is updated on every event and read by the real-time dashboard widget — it never queries ClickHouse for "right now."

- **Dashboard query cache**: Some ClickHouse aggregations (e.g., "monthly unique visitors for the past year") are expensive to compute. The result is cached in Redis for 60 seconds. If two dashboard users refresh within the same minute, ClickHouse is only queried once.

- **Rate limiting**: Each customer has an event ingestion limit. Redis counters enforce this so one customer can't flood the system and affect others. See [Rate Limiting](concepts.md#12-rate-limiting).

---

### Metadata Database — PostgreSQL
**What it is:** A relational database for structured app data. See [Relational Databases](concepts.md#3-relational-databases-sql).

**Why both PostgreSQL and ClickHouse?** They serve different purposes. PostgreSQL is the app's "operational" database — it stores accounts, settings, saved reports. ClickHouse is the "analytical" database — it stores the raw events. Each is optimized for its role. Using the wrong one for the other's workload would be significantly slower.

**What it stores:**
- `sites` — each business's tracked website
- `users` — dashboard user accounts
- `api_keys` — authentication keys for the ingestion SDK
- `saved_reports` — custom report configurations
- `alert_rules` — "notify me if traffic drops by 20%"

---

### Object Storage — S3 (production) / MinIO (local)
**What it is:** A service for storing and retrieving large files. See [Object Storage](concepts.md#7-object-storage).

**Why it's used here:** When a user exports a report as CSV or PDF, generating it is slow and the file can be large. The server generates the file asynchronously (in the background), uploads it to S3 (or MinIO locally), and emails the user a download link when it's ready. This way the export doesn't block the user's browser. See [Async Processing](concepts.md#15-async-processing-and-background-jobs).

**Running locally:** Use [MinIO](https://min.io/) — free, open-source, runs in Docker, fully S3-compatible.

---

## Data Flow

**Event ingestion (happens millions of times per second):**
1. Visitor loads a page → JS snippet fires a `page_view` event → POST to the ingestion API
2. Ingestion API publishes the event to Kafka and returns `200 OK` immediately
3. ClickHouse consumer reads events from Kafka and inserts them in micro-batches every few seconds

**Real-time dashboard widget:**
4. Dashboard polls every few seconds → server reads `ZCOUNT` from Redis → returns live visitor count instantly (no ClickHouse query)

**Historical chart (e.g., "page views per day for the last 30 days"):**
5. User opens dashboard → server checks Redis cache → cache miss → runs ClickHouse aggregation query → stores result in Redis with 60-second TTL → returns to browser

---

## Interesting Engineering Challenges

- **Exactly-once delivery**: Kafka guarantees every event is delivered at least once to consumers, but network issues can cause the same event to be delivered twice. ClickHouse must deduplicate these (using a unique event ID as a deduplication key) so the same event isn't counted twice in analytics.
- **Funnel analysis**: "How many users completed all 4 steps of checkout?" requires matching events by the same user across a sequence — a complex query across billions of rows. Optimizing this without it taking minutes requires careful data modeling.
- **Multi-tenant isolation**: Every customer's events are in the same ClickHouse table. Every query must filter by `site_id` to prevent one customer from seeing another's data. A missing filter anywhere is a data leak — this is an easy bug to introduce and a critical one to prevent.
