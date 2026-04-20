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
| Object Storage | Azure Blob / Azurite (local) | Product images and media |
| Queue | RabbitMQ (local) / CloudAMQP (cloud) | Async post-order tasks (email, warehouse notify) |

**Key challenge:** Preventing oversell during flash sales using optimistic locking or Redis atomic `DECR`.

---

## 2. Real-Time Chat Application
> [Full details](realtime_chat.md)

A messaging platform (à la Slack/Discord) for direct messages, group channels, and media sharing with real-time delivery and persistent history.

| Layer | Technology | Purpose |
|---|---|---|
| Primary DB | MongoDB | Messages and channels — flexible document schema |
| Cache / Pub-Sub | Redis | Fan-out via Pub/Sub, presence tracking, unread counts |
| Object Storage | Azure Blob / Azurite (local) | Uploaded files, images, voice messages |
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
| Queue | Kafka (local) / Azure Event Hubs (cloud) | Async click event pipeline to analytics |

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
| Object Storage | Azure Blob / Azurite (local) | Exported CSV/PDF reports |

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
| Queue | RabbitMQ (local) / CloudAMQP (cloud) | Async reminder notifications (24h, 2h before reservation) |

**Key challenge:** Preventing double-booking under concurrent requests using a Redis distributed lock around the booking transaction.

---

## 6. Social Media Feed
> [Full details](social_feed.md)

A content-sharing platform (à la Twitter/Instagram) with personalized home feeds, follows, likes, comments, and trending topics.

| Layer | Technology | Purpose |
|---|---|---|
| Primary DB | PostgreSQL | Users, posts, follows, likes — source of truth |
| Cache | Redis | Pre-computed feed sorted sets, like/comment counters, trending hashtags, sessions |
| Object Storage | Azure Blob / Azurite (local); Azure Front Door / CDN optional | Images and videos served globally at low latency |
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
| Object Storage | Azure Blob / Azurite (local) | Resumes (PDF/DOCX) and company logos |
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
| **Azurite** *(local Azure Blob Storage emulator)* | Docker (`mcr.microsoft.com/azure-storage/azurite` image) | Microsoft's official emulator; implements the same Blob REST API and SAS scheme — code written for Azure Blob works against Azurite unchanged |
| **Sidekiq** | Ruby gem — runs in-process | Free, open-source |
| **BullMQ** | npm package — runs in-process | Free, open-source |

### Cloud services and their local replacements

Two services in these app ideas are cloud-hosted products. Neither is required for local development:

| Cloud Service | Local Replacement | How |
|---|---|---|
| **Azure Blob Storage** | **Azurite** | Microsoft's official emulator; same SDK and REST API |
| **Azure Service Bus** | **RabbitMQ** | Both are message queues; RabbitMQ runs locally in Docker (note: switching the SDK from `pika` to `azure-servicebus` is required for the cloud side) |
| **Azure Front Door / CDN** | *(skip locally)* | Serve files directly from Azurite or your local server; a CDN is only needed for global production traffic |

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

  azurite:
    image: mcr.microsoft.com/azure-storage/azurite
    command: "azurite-blob --blobHost 0.0.0.0"
    ports: ["10000:10000"]

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
| **Azure Service Bus** | No *(use RabbitMQ locally)* | Managed cloud queue with minimal ops overhead |

### Object Storage
| Technology | Local? | Best For |
|---|---|---|
| **Azurite** | Yes (Docker) | Local development — Microsoft's official Azure Blob Storage emulator |
| **Azure Blob Storage** | No *(use Azurite locally)* | Production object storage; Google Cloud Storage is an equivalent option on GCP |

### Further Reading
- PostgreSQL documentation — https://www.postgresql.org/docs/
- Redis documentation — https://redis.io/docs/
- Elasticsearch documentation — https://www.elastic.co/guide/index.html
- Apache Kafka documentation — https://kafka.apache.org/documentation/
- ClickHouse documentation — https://clickhouse.com/docs/
- MongoDB documentation — https://www.mongodb.com/docs/
- System Design Primer (GitHub) — https://github.com/donnemartin/system-design-primer
- Designing Data-Intensive Applications (Kleppmann, 2017) — covers databases, replication, stream processing
