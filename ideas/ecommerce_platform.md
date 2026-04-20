# E-Commerce Platform

> **New to web apps?** Read [concepts.md](concepts.md) first — it explains databases, caches, message queues, and other building blocks used throughout this document.

## Overview
A full-featured online storefront where customers browse products, manage carts, and place orders. Sellers can manage inventory and view sales analytics.

Think of it as building Amazon at a smaller scale: customers need to search for products, add them to a cart, and pay — all without two people accidentally buying the last item in stock at the same time.

## Key Features
- Product catalog with search and filtering
- Shopping cart and checkout flow
- Order management and tracking
- Inventory management for sellers
- Product recommendations

---

## Infrastructure

### Primary Database — PostgreSQL
**What it is:** A relational (SQL) database — data is stored in structured tables with rows and columns, and tables can reference each other. See [Relational Databases](concepts.md#3-relational-databases-sql).

**Why it's used here:** An e-commerce app has a web of related data — a product belongs to a seller, an order belongs to a customer, an order contains many products. Relational tables model these relationships cleanly.

**What it stores:**
- `users` — customer and seller accounts
- `sellers` — seller profiles and settings
- `products` — name, description, price, stock count
- `orders` — who ordered what and when
- `order_items` — the individual line items within an order
- `reviews` — customer ratings and written feedback

**Key behavior — ACID transactions at checkout:** When a customer checks out, two things must happen together: the product's stock count must decrease by 1, AND the order record must be created. If the system crashes between those two steps, you'd have a phantom order with no stock change (or vice versa). A **transaction** ensures both steps succeed or neither does. See [Transactions and ACID](concepts.md#13-transactions-and-acid).

---

### Cache — Redis
**What it is:** A fast in-memory store that holds temporary copies of frequently read data, drastically reducing the number of trips to the main database. See [The Cache](concepts.md#5-the-cache).

**Why it's used here:** Product pages are read thousands of times per minute but change rarely. Fetching the same product data from PostgreSQL on every request is wasteful. Redis stores a copy and answers instantly.

**How it's used:**
- **Session / cart data**: When a customer adds items to their cart before logging in, that cart lives in Redis tied to their browser session. The cart is associated with a short **TTL** (time-to-live) so it automatically clears if they abandon the session. See [TTL](concepts.md#14-ttl-time-to-live).
- **Product page cache**: The full product detail (name, price, images, reviews summary) is cached in Redis. A cache hit means no database query at all.
- **Rate limiting**: If someone hammers the checkout button repeatedly (or runs an automated script), Redis counters throttle them to a reasonable rate. See [Rate Limiting](concepts.md#12-rate-limiting).

---

### Search — Elasticsearch
**What it is:** A dedicated search engine that indexes data and answers text search queries extremely fast. See [Search Engines](concepts.md#8-search-engines).

**Why it's used here:** A regular database can find a product by exact ID but struggles to answer "show me all waterproof hiking boots under $100, sorted by rating." Elasticsearch is built for exactly that.

**How it's used:**
- **Full-text search with faceted filtering**: A customer types "hiking boots" and can filter by category, price range, and star rating simultaneously.
- **Autocomplete**: As the customer types, Elasticsearch suggests matching product names in real time.

---

### Object Storage — S3 (production) / MinIO (local)
**What it is:** A service for storing and serving large files (images, videos, documents). See [Object Storage](concepts.md#7-object-storage).

**Why it's used here:** Product images and seller-uploaded media are large binary files. Storing them in a database is inefficient and expensive. S3 stores them cheaply and serves them via URL, often with a CDN in front for fast global delivery. See [CDN](concepts.md#9-the-cdn-content-delivery-network).

**Running locally:** Use [MinIO](https://min.io/) — a free, open-source server that provides the exact same API as S3. You point your code at `localhost:9000` instead of an AWS endpoint and everything works identically. No AWS account or payment needed.

---

### Message Queue — RabbitMQ (local) / SQS (managed cloud)
**What it is:** A buffer that lets the web server hand off slow or non-urgent work to background workers. See [The Message Queue](concepts.md#6-the-message-queue).

**Why it's used here:** After an order is placed, several things need to happen — send a confirmation email, notify the warehouse to fulfill it, update sales analytics. None of these should make the customer wait. The server drops a message into the queue ("order #1234 was placed") and immediately confirms the purchase to the customer. Background workers pick up the message and handle each task at their own pace. See [Async Processing](concepts.md#15-async-processing-and-background-jobs).

---

## Data Flow

Here's how a typical purchase flows through the system from start to finish:

1. **Customer searches** → query goes to Elasticsearch → ranked product list returned
2. **Customer views a product** → server checks Redis cache first; if the product is cached, it returns immediately; if not (cache miss), it queries PostgreSQL, then saves the result to Redis for next time
3. **Customer adds to cart** → Redis session is updated with the new cart contents
4. **Customer checks out** → PostgreSQL transaction runs: confirm stock exists, create the order record, decrement the stock count — all atomically
5. **Order confirmed** → server publishes an event to the message queue → email worker sends confirmation → warehouse worker begins fulfillment

---

## Interesting Engineering Challenges

- **Preventing oversell during flash sales**: If 500 customers try to buy the last item at the same moment, naive code could sell it 500 times. The solution uses either optimistic locking (detect conflicts and retry) or Redis's atomic `DECR` command (decrement and check in one operation, which can't be interrupted).
- **Cache invalidation**: When a seller updates a product's price, the old cached version must be removed from Redis immediately, or customers will see wrong prices. Getting this right without accidentally clearing too much (or too little) cache is a classic problem.
- **Paginating large product catalogs**: A query returning 50,000 products is too slow and too large to send to the browser. Cursor-based pagination loads results in chunks efficiently.
