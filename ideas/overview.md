# Web App Sample Ideas — Overview

A collection of web application concepts that demonstrate common backend patterns: relational databases, caching layers, search engines, message queues, and object storage. Each idea is designed to illustrate realistic architectural tradeoffs a client or customer might encounter.

> **New to web apps?** Start with [concepts.md](concepts.md) — it explains the foundational building blocks (databases, caches, queues, WebSockets, and more) that all of these apps share, in plain language.

---

## Table of Contents

- [Core Concepts](concepts.md) ← start here if you're new to web apps
1. [E-Commerce Platform](#1-e-commerce-platform)
2. [Real-Time Chat Application](#2-real-time-chat-application)
3. [URL Shortener Service](#3-url-shortener-service)
4. [Analytics Dashboard](#4-analytics-dashboard)
5. [Restaurant Reservation System](#5-restaurant-reservation-system)
6. [Social Media Feed](#6-social-media-feed)
7. [Job Board & Applicant Tracking System](#7-job-board--applicant-tracking-system)
8. [Running Locally (Free, No Hosting Required)](#running-locally-free-no-hosting-required)
9. [Technology Reference](#technology-reference)

---

## 1. E-Commerce Platform
> [Full details](ecommerce_platform.md)

An online storefront where customers browse products, manage carts, and place orders; sellers manage inventory and view sales analytics.

| Layer | Technology | Purpose |
|---|---|---|
| Primary DB | PostgreSQL | Products, orders, inventory — ACID transactions for checkout |
| Cache | Redis | Cart sessions, product page cache, rate limiting |
| Search | Elasticsearch | Full-text product search, autocomplete |
| Object Storage | S3 / MinIO (local) | Product images and media |
| Queue | RabbitMQ (local) / SQS (cloud) | Async post-order tasks (email, warehouse notify) |

**Key challenge:** Preventing oversell during flash sales using optimistic locking or Redis atomic `DECR`.

---

## 2. Real-Time Chat Application
> [Full details](realtime_chat.md)

A messaging platform (à la Slack/Discord) for direct messages, group channels, and media sharing with real-time delivery and persistent history.

| Layer | Technology | Purpose |
|---|---|---|
| Primary DB | MongoDB | Messages and channels — flexible document schema |
| Cache / Pub-Sub | Redis | Fan-out via Pub/Sub, presence tracking, unread counts |
| Object Storage | S3 / MinIO (local) | Uploaded files, images, voice messages |
| Transport | WebSockets | Stateful real-time connections per client |

**Key challenge:** Scaling WebSocket servers horizontally using Redis as the cross-instance message bus.

---

## 3. URL Shortener Service
> [Full details](url_shortener.md)

A high-throughput service mapping short codes to long URLs. Reads (redirects) vastly outnumber writes, making caching the central design concern.

| Layer | Technology | Purpose |
|---|---|---|
| Primary DB | PostgreSQL | URL mappings, expiration dates, owners |
| Cache | Redis | Redirect cache (near 100% hit rate), rate limiting, ID generation via `INCR` |
| Analytics DB | ClickHouse | Aggregate click events for reporting |
| Queue | Kafka (local) / SQS (cloud) | Async click event pipeline to analytics |

**Key challenge:** Sub-millisecond redirect latency — a single Redis round trip should satisfy nearly all requests.

---

## 4. Analytics Dashboard
> [Full details](analytics_dashboard.md)

A SaaS platform where businesses embed a JS snippet to track user events and visualize them through real-time and historical dashboards.

| Layer | Technology | Purpose |
|---|---|---|
| Event Bus | Apache Kafka | High-throughput event ingestion; decouples capture from processing |
| Time-Series DB | ClickHouse | Columnar storage for fast aggregation over billions of rows |
| Cache | Redis | Real-time visitor counters, dashboard query cache, rate limiting |
| Metadata DB | PostgreSQL | Sites, users, API keys, saved reports |
| Object Storage | S3 / MinIO (local) | Exported CSV/PDF reports |

**Key challenge:** Exactly-once delivery from Kafka to ClickHouse using deduplication keys.

---

## 5. Restaurant Reservation System
> [Full details](restaurant_reservation.md)

A booking platform (à la OpenTable) where diners check real-time availability and reserve tables; restaurants manage floor plans and guest history.

| Layer | Technology | Purpose |
|---|---|---|
| Primary DB | PostgreSQL | Restaurants, tables, time slots, reservations — `SELECT FOR UPDATE` for booking |
| Cache | Redis | Availability cache, search result cache, distributed booking lock |
| Search | Elasticsearch / PostGIS | Geo-distance restaurant search, cuisine/rating filters |
| Queue | RabbitMQ (local) / SQS (cloud) | Async reminder notifications (24h, 2h before reservation) |

**Key challenge:** Preventing double-booking under concurrent requests using a Redis distributed lock around the booking transaction.

---

## 6. Social Media Feed
> [Full details](social_feed.md)

A content-sharing platform (à la Twitter/Instagram) with personalized home feeds, follows, likes, comments, and trending topics.

| Layer | Technology | Purpose |
|---|---|---|
| Primary DB | PostgreSQL | Users, posts, follows, likes — source of truth |
| Cache | Redis | Pre-computed feed sorted sets, like/comment counters, trending hashtags, sessions |
| Object Storage | S3 / MinIO (local); CDN optional | Images and videos served globally at low latency |
| Search | Elasticsearch | User and hashtag search |
| Event Bus | Kafka | Fan-out post events to feed, notification, and search indexer services |

**Key challenge:** The "celebrity problem" — fan-out on write is too expensive for accounts with millions of followers; hybrid fan-out strategies are required.

---

## 7. Job Board & Applicant Tracking System
> [Full details](job_board.md)

A two-sided marketplace where companies post jobs, candidates apply, and recruiters manage hiring pipelines with smart search and recommendations.

| Layer | Technology | Purpose |
|---|---|---|
| Primary DB | PostgreSQL | Companies, jobs, candidates, applications, pipeline stages |
| Cache | Redis | Listing cache, search result cache, session storage, rate limiting |
| Search | Elasticsearch | Full-text job search, geo-distance, skills-based candidate search |
| Object Storage | S3 / MinIO (local) | Resumes (PDF/DOCX) and company logos |
| Job Queue | Sidekiq / BullMQ | Status-change emails, listing expiry, recommendation scoring |

**Key challenge:** Ranking search results by recency, relevance, and candidate–job fit simultaneously.

---

## Running Locally (Free, No Hosting Required)

Every app in this collection can be built and tested entirely on your own machine at no cost. The table below maps each technology to its local setup method. All of these are free and open-source.

The recommended approach is **Docker + Docker Compose**: instead of installing each service separately, you define all the services your app needs in a single `docker-compose.yml` file and start them all with one command (`docker compose up`). Docker Desktop is free for personal use.

| Technology | Local Setup | Notes |
|---|---|---|
| **PostgreSQL** | Docker (`postgres` image) or install directly | Free, open-source |
| **MongoDB** | Docker (`mongo` image) or MongoDB Community Edition | Free, open-source |
| **Redis** | Docker (`redis` image) or install directly | Free, open-source |
| **Elasticsearch** | Docker (`elasticsearch` image) | Free for local dev; [OpenSearch](https://opensearch.org/) is a fully open-source alternative |
| **Apache Kafka** | Docker (`confluentinc/cp-kafka` or `bitnami/kafka`) | Free, open-source; needs a ZooKeeper or KRaft sidecar |
| **RabbitMQ** | Docker (`rabbitmq` image) | Free, open-source |
| **ClickHouse** | Docker (`clickhouse/clickhouse-server` image) | Free, open-source |
| **MinIO** *(local S3 replacement)* | Docker (`minio/minio` image) | Free, open-source; fully S3-compatible API — code written for S3 works against MinIO unchanged |
| **Sidekiq** | Ruby gem — runs in-process | Free, open-source |
| **BullMQ** | npm package — runs in-process | Free, open-source |

### Cloud services and their local replacements

Two services in these app ideas are cloud-hosted products. Neither is required for local development:

| Cloud Service | Local Replacement | How |
|---|---|---|
| **AWS S3** | **MinIO** | S3-compatible API; swap the endpoint URL in your config |
| **AWS SQS** | **RabbitMQ** | Both are message queues; RabbitMQ runs locally in Docker |
| **CDN** | *(skip locally)* | Serve files directly from MinIO or your local server; a CDN is only needed for global production traffic |

### Example `docker-compose.yml` skeleton

This shows how you might start the core services for most apps in this collection:

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_PASSWORD: secret
    ports: ["5432:5432"]

  redis:
    image: redis:7
    ports: ["6379:6379"]

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports: ["9000:9000", "9001:9001"]

  elasticsearch:
    image: elasticsearch:8.13.0
    environment:
      discovery.type: single-node
      xpack.security.enabled: "false"
    ports: ["9200:9200"]

  rabbitmq:
    image: rabbitmq:3-management
    ports: ["5672:5672", "15672:15672"]  # 15672 is the admin UI
```

Add or remove services based on which app you're building. Start everything with `docker compose up -d`.

---

## Technology Reference

### Databases
| Technology | Local? | Type | Best For |
|---|---|---|---|
| **PostgreSQL** | Yes (Docker) | Relational (SQL) | Structured data with relationships, ACID transactions |
| **MongoDB** | Yes (Docker) | Document (NoSQL) | Flexible schemas, hierarchical/nested data |
| **ClickHouse** | Yes (Docker) | Columnar (OLAP) | Analytical queries over large volumes of append-only events |

### Caching
| Technology | Local? | Best For |
|---|---|---|
| **Redis** | Yes (Docker) | General-purpose cache, Pub/Sub, distributed locks, atomic counters, sorted sets |

### Search
| Technology | Local? | Best For |
|---|---|---|
| **Elasticsearch** | Yes (Docker) | Full-text search, faceted filtering, geo-distance queries, autocomplete |
| **PostGIS** | Yes (PostgreSQL extension) | Geospatial queries within PostgreSQL (simpler stack, less scale) |

### Message Queues & Streaming
| Technology | Local? | Best For |
|---|---|---|
| **Apache Kafka** | Yes (Docker) | High-throughput durable event streaming, fan-out to multiple consumers |
| **RabbitMQ** | Yes (Docker) | Task queues, routing, work distribution |
| **AWS SQS** | No *(use RabbitMQ locally)* | Managed cloud queue with minimal ops overhead |

### Object Storage
| Technology | Local? | Best For |
|---|---|---|
| **MinIO** | Yes (Docker) | Local development — free, open-source, fully S3-compatible |
| **AWS S3** | No *(use MinIO locally)* | Production object storage; also GCS and Azure Blob Storage are equivalent cloud options |

### Further Reading
- PostgreSQL documentation — https://www.postgresql.org/docs/
- Redis documentation — https://redis.io/docs/
- Elasticsearch documentation — https://www.elastic.co/guide/index.html
- Apache Kafka documentation — https://kafka.apache.org/documentation/
- ClickHouse documentation — https://clickhouse.com/docs/
- MongoDB documentation — https://www.mongodb.com/docs/
- System Design Primer (GitHub) — https://github.com/donnemartin/system-design-primer
- Designing Data-Intensive Applications (Kleppmann, 2017) — covers databases, replication, stream processing
