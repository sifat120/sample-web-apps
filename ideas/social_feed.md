# Social Media Feed

> **New to web apps?** Read [concepts.md](concepts.md) first — it explains databases, caches, message queues, and other building blocks used throughout this document.

## Overview
A content-sharing platform where users post updates, follow others, and see a personalized feed of content from the people they follow — similar to Twitter/X or Instagram.

The hardest problem here is the **feed**: when you open the app, you need to see the latest posts from everyone you follow, in roughly chronological order, in under a second. With potentially millions of users all doing this at once, generating each person's feed from scratch every time is not feasible. The solution involves pre-computing feeds and caching them.

## Key Features
- Create posts (text, images, video)
- Follow / unfollow users
- Personalized home feed
- Likes, comments, reposts
- Notifications (new follower, like, comment)
- Trending topics / hashtags

---

## Infrastructure

### Primary Database — PostgreSQL
**What it is:** A relational database that stores structured data in tables. See [Relational Databases](concepts.md#3-relational-databases-sql).

**Why it's used here:** User accounts, follow relationships, posts, and likes are all well-structured relational data. PostgreSQL is the **source of truth** — the authoritative record of everything that has happened. Other components (caches, queues) may have slightly stale copies, but PostgreSQL always has the correct, final version.

**What it stores:**
- `users` — profiles, bios, follower/following counts
- `posts` — the actual content (text, media reference, timestamp)
- `follows` — which user follows which other user
- `likes` — which user liked which post
- `comments` — comment text linked to a post and author
- `hashtags` and `post_hashtags` — the many-to-many relationship between posts and their tags

---

### Cache — Redis
**What it is:** A fast in-memory store that supports more than simple key-value pairs — it has lists, sorted sets, counters, and more. See [The Cache](concepts.md#5-the-cache).

**This is the most complex use of Redis in any app in this collection.** Here's how each feature maps to a Redis data structure:

- **Feed cache (pre-computed, sorted set)**: Each user has a Redis sorted set — a list where every item has a numeric score. For feeds, the score is the post's timestamp and each item is a post ID. When Alice opens her feed, the server reads her sorted set (the top 20 items by score) and then fetches those posts' full details from PostgreSQL or a post cache. This is much faster than querying "give me the 20 most recent posts from all 300 people Alice follows" in real time.

  When someone Alice follows posts, their new post ID is pushed into Alice's feed sorted set — this is called **fan-out on write**. See [Fan-Out](concepts.md#17-fan-out).

- **Like and comment counters**: Exact like counts don't need to be perfectly up to date — a post showing "1,247 likes" vs "1,248 likes" is fine. Redis counters are incremented immediately when someone likes a post (very fast), and periodically synced to PostgreSQL in the background. This avoids hammering PostgreSQL with a write on every single like.

- **Trending hashtags (sorted set with decayed scoring)**: Redis tracks how many times each hashtag has been used recently. The score decreases over time so yesterday's trending tags fall off the list automatically.

- **Session tokens**: Logged-in users have their session stored in Redis. See [Sessions and Authentication](concepts.md#11-sessions-and-authentication).

---

### Object Storage — S3 + CDN (production) / MinIO (local)
**What it is:** S3 stores large files (images, videos). A CDN distributes copies of those files to servers around the world for fast access. See [Object Storage](concepts.md#7-object-storage) and [CDN](concepts.md#9-the-cdn-content-delivery-network).

**Why both?** A post's image is uploaded once to S3 (the permanent store) but viewed potentially millions of times by users all over the world. The CDN caches the image at edge servers near each user — a viewer in Tokyo gets the image from a server in Tokyo, not a data center in Virginia. This cuts load times from hundreds of milliseconds to tens of milliseconds.

**Running locally:** Use [MinIO](https://min.io/) instead of S3 — it's free, open-source, runs in Docker, and has an identical API. Skip the CDN entirely for local development; your browser fetches images directly from MinIO at `localhost:9000`. The CDN is a production-only performance concern.

---

### Search — Elasticsearch
**What it is:** A dedicated search engine for fast text queries. See [Search Engines](concepts.md#8-search-engines).

**Why it's used here:** Users want to search for other users by name or handle, and search posts by hashtag or keyword. These full-text queries are a poor fit for PostgreSQL but are exactly what Elasticsearch is designed for.

---

### Message Queue — Kafka
**What it is:** A high-throughput event streaming system. See [The Message Queue](concepts.md#6-the-message-queue).

**Why Kafka specifically (vs. a simpler queue)?** When Alice posts, multiple independent systems need to react:
1. The **feed service** must push Alice's post to all her followers' feed caches
2. The **notification service** must notify her followers
3. The **search indexer** must index the new post so it appears in search results

Kafka lets all three consumers independently read the same "new post" event without any of them knowing about the others. Adding a fourth consumer in the future (e.g., a content moderation service) requires no changes to the existing consumers. This is [fan-out](concepts.md#17-fan-out) at the event-streaming layer.

---

## Data Flow

**Posting:**
1. User submits a post → saved to PostgreSQL (permanent record)
2. Server publishes a "new post" event to Kafka
3. **Feed service** consumes the event → pushes the new post ID into each follower's Redis feed sorted set
4. **Notification service** consumes the event → queues notifications for followers
5. **Search indexer** consumes the event → indexes the post in Elasticsearch

**Loading the feed:**
6. User opens app → server reads their Redis feed sorted set (top 20 post IDs by score)
7. Server batch-fetches post details for those IDs from PostgreSQL (or a post detail cache in Redis)
8. Feed is returned to the browser

**Liking a post:**
9. User taps like → Redis like counter is incremented (`INCR`) instantly
10. A background job periodically flushes accumulated like counts from Redis to PostgreSQL

---

## Interesting Engineering Challenges

- **The celebrity problem**: If a user has 10 million followers, fan-out on write means pushing their post into 10 million Redis sorted sets simultaneously — an enormous write operation that could lag behind by minutes. The solution is a hybrid: fan-out on write for regular users, fan-out on read for celebrity accounts (their posts are fetched and merged into the feed at read time). See [Fan-Out](concepts.md#17-fan-out).
- **Feed staleness vs. latency**: Pre-computed feeds in Redis are fast to read but may be slightly stale (a post from 30 seconds ago might not have been pushed yet). This is an intentional trade-off — perfect freshness would require real-time computation that can't scale.
- **Eventual consistency between Redis and PostgreSQL**: The like counter in Redis and the `likes` column in PostgreSQL can temporarily disagree. Eventually they converge (after the periodic sync), but for a brief window, different parts of the system may report different counts. This is a normal and accepted property of high-scale systems.
