# Core Web App Concepts

This document explains the fundamental building blocks that appear across all the web app ideas in this collection. If you're new to web development, start here before reading any of the individual app files.

---

## Table of Contents

1. [How a Web App Works](#1-how-a-web-app-works)
2. [The Database](#2-the-database)
3. [Relational Databases (SQL)](#3-relational-databases-sql)
4. [Document Databases (NoSQL)](#4-document-databases-nosql)
5. [The Cache](#5-the-cache)
6. [The Message Queue](#6-the-message-queue)
7. [Object Storage](#7-object-storage)
8. [Search Engines](#8-search-engines)
9. [The CDN (Content Delivery Network)](#9-the-cdn-content-delivery-network)
10. [WebSockets](#10-websockets)
11. [Sessions and Authentication](#11-sessions-and-authentication)
12. [Rate Limiting](#12-rate-limiting)
13. [Transactions and ACID](#13-transactions-and-acid)
14. [TTL (Time-To-Live)](#14-ttl-time-to-live)
15. [Async Processing and Background Jobs](#15-async-processing-and-background-jobs)
16. [Horizontal Scaling](#16-horizontal-scaling)
17. [Fan-Out](#17-fan-out)

---

## 1. How a Web App Works

When you visit a website, your browser (the **client**) sends a request over the internet to a **server** — a computer running software that knows how to respond to that request.

```
Browser  ──── request ────►  Server  ──── query ────►  Database
         ◄─── response ────           ◄─── data  ────
```

- The **client** is what runs in your browser (HTML, CSS, JavaScript).
- The **server** is the backend — it processes requests, applies business logic, and fetches or saves data.
- The **database** is where the data lives permanently. The server asks the database for data, and the database returns it.

Most web apps also have several other components beyond the basic server + database pair — that's what the rest of this document covers.

---

## 2. The Database

A database is a program designed specifically for storing data reliably and allowing fast retrieval. Unlike saving data to a plain file, a database gives you:

- **Structured storage**: data is organized into tables, rows, or documents
- **Fast lookups**: databases build internal indexes so they can find a specific record instantly, even among millions
- **Concurrent access**: many users can read and write at the same time without corrupting each other's data
- **Durability**: data survives server restarts and crashes

There are two main families of databases used in these apps: **relational (SQL)** and **document (NoSQL)**.

---

## 3. Relational Databases (SQL)

A relational database organizes data into **tables** — like spreadsheets with rows and columns. Every row in a table represents one record, and every column represents a field of that record.

**Example — a `users` table:**

| id | name    | email               | created_at          |
|----|---------|---------------------|---------------------|
| 1  | Alice   | alice@example.com   | 2024-01-10 09:00:00 |
| 2  | Bob     | bob@example.com     | 2024-02-05 14:30:00 |

Tables can reference each other. An `orders` table might have a `user_id` column pointing to the `users` table — that's the "relational" part.

You query a relational database using **SQL** (Structured Query Language):
```sql
SELECT * FROM users WHERE email = 'alice@example.com';
```

**PostgreSQL** is a popular open-source relational database used heavily throughout these apps. It's a great default choice when your data has clear relationships and structure.

**Best for:** user accounts, orders, products, reservations — anything with clear relationships and a need for strict data integrity.

---

## 4. Document Databases (NoSQL)

A document database stores data as **documents** — typically JSON-like objects — instead of rows in a table. Documents can have nested fields and don't all need to look the same.

**Example — a `messages` document:**
```json
{
  "id": "msg_001",
  "channel_id": "ch_general",
  "author": "alice",
  "text": "Hello everyone!",
  "reactions": [
    { "emoji": "👍", "count": 3 }
  ],
  "pinned": false
}
```

This is more flexible than a relational table: one message might have reactions, another might not. In a relational database, you'd need a separate `reactions` table; in a document database it's just an embedded list.

**MongoDB** is the most common document database. It's a great fit when data is naturally hierarchical (nested), when the schema (structure) might change over time, or when you're storing content that varies message-to-message.

**Best for:** chat messages, content posts, product catalogs with variable attributes.

---

## 5. The Cache

A **cache** is a fast, temporary store that holds copies of data your app reads frequently. The idea is simple: reading data from a database involves a network round-trip and disk access, which can take tens of milliseconds. Reading from a cache (which lives in memory) takes under a millisecond.

```
Request ──► Cache hit?  ──YES──► Return data immediately (fast)
                │
               NO
                │
                ▼
            Database ──────────► Return data + save copy to cache
```

A cache improves performance dramatically for data that:
- Is read many more times than it's written
- Doesn't need to be perfectly up to the millisecond (e.g., product listings)

**Cache miss**: the data isn't in the cache yet, so the app falls back to the database, fetches it, and stores a copy in the cache for next time.

**Cache invalidation**: when the underlying data changes (e.g., a product price is updated), the cached copy needs to be removed or updated so stale data isn't served.

**Redis** is the most popular caching layer. It stores everything in memory and supports many data structures (strings, lists, sorted sets, hash maps), making it useful for more than just simple caching — it's also used for rate limiting, counters, pub/sub messaging, and distributed locks.

**Best for:** product pages, search results, user sessions, counters, any data that's expensive to compute and read often.

---

## 6. The Message Queue

A **message queue** is a buffer that holds tasks or events to be processed later, by a separate worker process. Instead of doing work immediately inside the request handler, the server drops a message into the queue and returns a response right away. A worker picks up the message and does the work in the background.

```
Web Server ──► Queue ──► Worker Process
  (fast)        │              │
                │         (slow work: send email,
                │          resize image, update stats)
                │
               messages wait here if worker is busy
```

**Why bother?** Some tasks are slow (sending an email, processing a video, calling a third-party API) or don't need to complete before you respond to the user. Queueing them keeps the web server fast and responsive.

**Common tools:**
- **RabbitMQ** — general-purpose task queues
- **Apache Kafka** — built for extremely high volumes; every event is durably stored and can be replayed; multiple consumers can read the same events independently
- **AWS SQS** — a managed (hosted) queue; minimal setup and maintenance

**Best for:** sending emails/SMS, processing uploads, updating analytics, notifying other services of events.

---

## 7. Object Storage

A **database** stores structured records (rows, documents). But what about large binary files — images, videos, PDFs, audio clips? Storing them in a database is wasteful and slow.

**Object storage** is a service designed for exactly this: storing and retrieving large files cheaply and reliably. You upload a file and get back a URL to retrieve it later.

**AWS S3** (Simple Storage Service) is the most widely used object storage. Equivalents include Google Cloud Storage and Azure Blob Storage. For self-hosted setups, **MinIO** is a popular open-source alternative.

Objects (files) are organized into **buckets** (like top-level folders). Each object has a unique key (filename/path) within its bucket.

**Best for:** profile pictures, product images, uploaded documents (resumes, invoices), video files, exported reports.

---

## 8. Search Engines

A regular database can find a row by exact match very quickly (e.g., `WHERE id = 42`). But "search" — finding all products whose description *mentions* "waterproof hiking boot" and ranking them by relevance — is a very different problem. Databases are bad at it.

A **search engine** (also called a search index) is a specialized store that is designed for text search. It pre-processes text by breaking it into individual words, removing common words ("the", "a"), and building an **inverted index**: a map from every word to every document that contains it.

```
Word "waterproof" → [product_12, product_47, product_203]
Word "boot"       → [product_12, product_47, product_88, product_301]
```

Searching for "waterproof boot" finds the intersection instantly and ranks results by how often and prominently the words appear.

**Elasticsearch** is the most popular search engine for web apps. Beyond text search, it also supports:
- **Faceted filtering**: "show me results filtered by price range and category"
- **Autocomplete / type-ahead**: suggestions as you type
- **Geo-distance queries**: "find restaurants within 5 miles"

**Best for:** product search, job search, full-text content search, location-based search.

---

## 9. The CDN (Content Delivery Network)

A CDN is a global network of servers (called **edge nodes**) placed in data centers all over the world. When a user requests a file (like an image or video), instead of fetching it from your central server, they fetch it from the nearest edge node.

```
User in Tokyo ──► CDN edge in Tokyo (fast, <20ms)
                  instead of
User in Tokyo ──► Your server in Virginia (slow, ~200ms)
```

CDNs cache static files at the edge so that users everywhere get fast load times, and your origin server doesn't have to serve every request directly.

**Best for:** serving images, videos, CSS, JavaScript, and any other static files to a global audience.

---

## 10. WebSockets

**HTTP** (the standard protocol browsers use) is request-response: the browser asks, the server answers, the connection closes. This works fine for loading pages, but it's not suitable for real-time apps — you can't have the server push a new message to you without you asking first.

**WebSockets** solve this by keeping a persistent, two-way connection open between the browser and server. Once connected, either side can send data to the other at any time — no need for the client to keep asking.

```
HTTP:       Client ──ask──► Server ──answer──► (done)
WebSocket:  Client ◄══════════════════════════► Server  (open forever)
                         messages flow both ways, anytime
```

**Best for:** real-time chat, live notifications, collaborative editing, live dashboards, multiplayer games.

---

## 11. Sessions and Authentication

When you log in to a web app, the server needs to remember who you are for all your subsequent requests. HTTP is **stateless** by default — each request arrives with no memory of previous ones.

A **session** solves this. After login, the server generates a unique **session token** (a random string) and stores it — either in the database, or in a fast cache like Redis. The browser saves the token in a cookie. On every future request, the browser sends the cookie, the server looks up the token, and knows who you are.

**Authentication** is the process of verifying identity (are you really Alice?). Common methods include password-based login, OAuth ("Sign in with Google"), and API keys.

---

## 12. Rate Limiting

**Rate limiting** restricts how many requests a user, IP address, or API key can make within a given time window. Without it, a single bad actor (or a runaway script) could flood your server with requests and make the app unusable for everyone else.

**Example:** allow no more than 5 checkout attempts per IP per minute.

Redis is commonly used to implement rate limiting because its atomic increment operations (`INCR`) let you count requests safely even when your app is running on many servers simultaneously.

---

## 13. Transactions and ACID

A **transaction** is a group of database operations that are treated as a single unit. Either all of them succeed together, or none of them do.

**Example — a checkout:**
1. Decrement product stock by 1
2. Create the order record
3. Charge the customer

If step 2 fails midway, you don't want step 1 to have already decremented stock. A transaction ensures all three steps happen atomically — as one indivisible operation.

**ACID** describes the guarantees a database transaction provides:
- **Atomicity**: all-or-nothing (if one step fails, all are rolled back)
- **Consistency**: the database is always left in a valid state
- **Isolation**: concurrent transactions don't interfere with each other
- **Durability**: once committed, data survives crashes

Relational databases like PostgreSQL provide full ACID guarantees. Many NoSQL databases trade some of these guarantees for speed or flexibility.

---

## 14. TTL (Time-To-Live)

A **TTL** is a timer attached to a piece of cached data that says "automatically delete this after N seconds." It's how caches stay fresh — instead of caching product prices forever, you might cache them for 60 seconds, after which the next request fetches a fresh copy from the database.

TTLs are also used for:
- **Session expiry**: log users out after 30 days of inactivity
- **Short-lived links**: a password-reset link that expires after 10 minutes
- **Presence indicators**: "online" status stored with a 30-second TTL; if not refreshed, the user appears offline

---

## 15. Async Processing and Background Jobs

**Synchronous** processing means: you ask for something, you wait, you get it back. That's fine for fast operations.

**Asynchronous (async)** processing means: you ask for something, the server says "got it, I'll handle it" and returns immediately, while the actual work happens later in the background.

Web apps use async processing for slow or non-urgent work:
- Sending a welcome email after signup (slow — external email service)
- Resizing an uploaded photo (CPU-intensive)
- Updating analytics counts (doesn't need to block the user)
- Notifying downstream services of an event

A **background job** is a unit of async work. Background jobs are typically managed by a job queue library (Sidekiq for Ruby, BullMQ for Node.js, Celery for Python). Workers — separate processes — pick jobs off the queue and execute them.

---

## 16. Horizontal Scaling

When a single server can't handle all incoming traffic, you can:

- **Scale vertically**: get a bigger server (more CPU, more RAM) — limited and expensive
- **Scale horizontally**: add more servers running the same code and distribute traffic across them

A **load balancer** sits in front of multiple server instances and routes each incoming request to one of them.

Horizontal scaling introduces new challenges: if a user's session is stored in memory on Server A, and their next request goes to Server B, Server B doesn't know who they are. Solutions include storing sessions in a shared store (like Redis) that all servers can access.

---

## 17. Fan-Out

**Fan-out** describes delivering one event to many recipients. The term comes from electronics (one signal → many outputs) but applies to web apps when one action needs to update many places.

**Example — social media post:**
- User A posts an update
- User A has 1,000 followers
- All 1,000 followers' feeds need to show the new post

Two strategies:
- **Fan-out on write**: when the post is created, immediately push it to all 1,000 followers' feed caches. Fast reads later, but expensive write if someone has millions of followers.
- **Fan-out on read**: when a follower opens their feed, fetch the latest posts from everyone they follow at that moment. Simple writes, but slower reads.

Real apps often use a hybrid: fan-out on write for regular users, fan-out on read for celebrities with massive followings.
