# Real-Time Chat Application

> **New to web apps?** Read [concepts.md](concepts.md) first — it explains databases, caches, message queues, and other building blocks used throughout this document.

## Overview
A messaging platform supporting direct messages, group channels, and media sharing — similar to Slack or Discord. Messages are delivered in real time and persisted for history.

The central challenge here is **real time**: standard web apps respond when the user asks. Chat needs the server to push a new message to your screen the instant someone else sends it — without you having to refresh the page.

## Key Features
- Direct messages and group channels
- Real-time message delivery with presence indicators (online/typing)
- Message history with infinite scroll
- File and image sharing
- Unread counts and notifications

---

## Infrastructure

### Primary Database — MongoDB
**What it is:** A document database that stores data as flexible JSON-like objects instead of rigid tables. See [Document Databases](concepts.md#4-document-databases-nosql).

**Why it's used here instead of a relational database:** Chat messages naturally vary in structure — some have reactions, some have thread replies, some have attachments, some are system events. In a relational database, you'd need many separate tables for all of these and complex joins to reassemble a message. MongoDB lets a single message document contain all of its own data in one place:

```json
{
  "id": "msg_001",
  "channel": "general",
  "author": "alice",
  "text": "Hello!",
  "reactions": [{ "emoji": "👍", "users": ["bob", "carol"] }],
  "thread_replies": 3
}
```

**What it stores:**
- `users` — account profiles
- `channels` — channel names, members, settings
- `messages` — the full message content, reactions, thread counts
- `channel_members` — who is in which channel

---

### Cache — Redis
**What it is:** A fast in-memory store. Here it does double duty: standard caching AND real-time message delivery (Pub/Sub). See [The Cache](concepts.md#5-the-cache).

**Why it's used here:**

- **Pub/Sub for message fan-out**: When Alice sends a message to the #general channel, that message must be instantly delivered to everyone in the channel — even if they're connected to different server instances. Redis Pub/Sub lets any server publish an event to a named "channel", and every other server subscribed to that channel receives it immediately. Those servers then push the message down to their connected clients. This is a form of [fan-out](concepts.md#17-fan-out).

- **Presence tracking**: "Alice is online" and "Bob is typing..." are stored in Redis with very short TTLs (e.g., 30 seconds). Every few seconds your browser silently tells the server you're still active, which refreshes the TTL. If it's not refreshed, the TTL expires and you appear offline automatically. See [TTL](concepts.md#14-ttl-time-to-live).

- **Unread counts**: Each user has a counter per channel ("you have 5 unread messages in #general"). Redis can increment (`INCR`) and reset these counters atomically — meaning the operation is guaranteed to complete fully even if multiple servers touch the same counter at the same time.

---

### Object Storage — Azure Blob Storage (production) / Azurite (local)
**What it is:** A service for storing and retrieving large files by URL. See [Object Storage](concepts.md#7-object-storage).

**Why it's used here:** Users share images, files, and voice messages. These are far too large to store in MongoDB. Instead, the file is uploaded directly to Azure Blob from the browser using a **SAS (Shared Access Signature) URL** — a temporary URL that grants one-time upload permission, so the file never passes through your server.

**Running locally:** Use [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) — Microsoft's official Azure Blob emulator that runs in Docker and supports the same SAS URL workflow as production Azure Blob Storage.

---

### WebSocket Server
**What it is:** A persistent, two-way connection between a browser and server. See [WebSockets](concepts.md#10-websockets).

**Why it's used here:** Standard HTTP is one-directional (client asks, server answers). Chat requires the server to push messages to you the moment they arrive — without you asking. WebSockets keep an open connection so messages can flow in either direction at any time.

**Scaling challenge:** If your app runs on multiple server instances (to handle more users), a client connected to Server A and a client connected to Server B need to exchange messages. Redis Pub/Sub acts as the bridge: Server A publishes the message to Redis, Server B (subscribed to the same channel in Redis) receives it and delivers it to the right client. See [Horizontal Scaling](concepts.md#16-horizontal-scaling).

---

## Data Flow

Here's what happens when Alice sends "Hello!" to the #general channel:

1. Alice's browser sends an HTTP POST to the server with the message text
2. Server saves the message to MongoDB (permanent record)
3. Server publishes an event to Redis: "new message in #general"
4. All server instances subscribed to #general in Redis receive the event
5. Each server pushes the message via WebSocket to every client currently viewing #general
6. Bob's browser (on a different server instance) receives the message and displays it instantly
7. Bob's unread count is incremented in Redis (if he's not currently viewing that channel)

---

## Interesting Engineering Challenges

- **Scaling WebSocket servers**: Unlike regular HTTP servers that are stateless, each WebSocket server holds open connections. Adding more server instances requires Redis Pub/Sub to route messages across all of them — otherwise messages wouldn't reach users on different instances.
- **Cursor-based pagination for history**: When you scroll up to load older messages, the app needs to fetch the previous page efficiently. Using a cursor (the ID/timestamp of the oldest visible message) rather than page numbers prevents gaps or duplicates when new messages arrive.
- **Handling reconnects**: If a user loses internet briefly, their WebSocket disconnects. On reconnect, the app needs to fetch any messages sent during the gap without showing duplicates.
