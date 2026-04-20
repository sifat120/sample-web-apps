# Restaurant Reservation System

> **New to web apps?** Read [concepts.md](concepts.md) first — it explains databases, caches, message queues, and other building blocks used throughout this document.

## Overview
A booking platform where diners search for restaurants, check real-time table availability, and make reservations — similar to OpenTable or Resy. Restaurants log in to manage their floor plan, configure time slots, and view their guest history.

The central engineering challenge is **concurrency**: if two people try to book the last available table at the same moment, exactly one should succeed and the other should see "sorry, no longer available" — never a double-booking.

## Key Features
- Search restaurants by cuisine, location, date/time, and party size
- Real-time availability lookup
- Reservation creation, modification, and cancellation
- Waitlist management
- Guest history and preferences for returning customers
- Automated reminder notifications

---

## Infrastructure

### Primary Database — PostgreSQL
**What it is:** A relational database where data lives in tables with rows and columns. See [Relational Databases](concepts.md#3-relational-databases-sql).

**Why it's used here:** Reservations involve highly relational data — a reservation links a specific guest to a specific table at a specific time slot at a specific restaurant. Relational tables model this naturally, and PostgreSQL's transaction support is essential for preventing double-bookings.

**What it stores:**
- `restaurants` — name, address, cuisine, total capacity, hours
- `tables` — each physical table (number of seats, location in the room)
- `time_slots` — bookable intervals (e.g., 7:00 PM for party of 2–4)
- `reservations` — which guest booked which slot, confirmation status
- `guests` — diner profiles, dietary preferences, visit history
- `waitlist` — guests waiting for a spot if all slots are full

**Preventing double-bookings with `SELECT FOR UPDATE`:** When a guest tries to book a slot, the server runs a transaction that first locks that slot's row using `SELECT FOR UPDATE`. This prevents any other transaction from reading or modifying the same row until the booking is complete. One transaction succeeds; the concurrent one waits and then finds the slot already taken. See [Transactions and ACID](concepts.md#13-transactions-and-acid).

---

### Cache — Redis
**What it is:** A fast in-memory store that holds temporary copies of frequently read data. See [The Cache](concepts.md#5-the-cache).

**Why it's used here:** Availability lookups happen constantly — far more often than actual bookings. If every "is 7 PM available?" check hit PostgreSQL, the database would be overwhelmed. Redis caches availability so most lookups are answered in under a millisecond.

**How it's used:**

- **Availability cache**: For each restaurant, date, time, and party size combination, Redis stores the available slot count. Every time a reservation is created or cancelled, this cache is updated. This means 99% of availability checks never touch PostgreSQL.

- **Search result cache**: Common searches ("Italian restaurants in Seattle available this Saturday") are cached for a few minutes. The same query from different users hits Redis rather than re-running the search from scratch.

- **Distributed lock during booking**: Even though PostgreSQL's `SELECT FOR UPDATE` prevents the database from double-booking, there's a window where many requests pile up waiting for the lock. A Redis distributed lock acts as a guard before the database — only one request per time slot enters the booking transaction at a time. Others are told "slot being booked, try again momentarily." See [Transactions and ACID](concepts.md#13-transactions-and-acid).

- **Session storage**: Logged-in guest sessions are stored in Redis with a TTL for expiry. See [Sessions and Authentication](concepts.md#11-sessions-and-authentication) and [TTL](concepts.md#14-ttl-time-to-live).

---

### Search — Elasticsearch (or PostGIS + PostgreSQL)
**What it is:** A dedicated search engine for text and geo-distance queries. See [Search Engines](concepts.md#8-search-engines).

**Why it's used here:** Guests search with natural criteria: "Italian food, near me, available Saturday at 7 PM, party of 4." This involves full-text matching (cuisine type, restaurant name), geographic filtering (within 2 miles), and date/time availability — a combination that is difficult and slow to express in SQL across many restaurants.

Elasticsearch handles geo-distance queries natively: "find all restaurants within 3 miles of these GPS coordinates."

**Alternative — PostGIS:** For smaller scale, the PostGIS extension for PostgreSQL adds geospatial query support without needing a separate search service. Simpler to operate, but doesn't scale as high.

---

### Message Queue — RabbitMQ (local) / CloudAMQP or Azure Service Bus (managed cloud)
**What it is:** A buffer for slow, non-urgent background work. See [The Message Queue](concepts.md#6-the-message-queue).

**Why it's used here:** After a reservation is confirmed, a reminder needs to be sent 24 hours before and again 2 hours before the reservation. This is a scheduled future task — the server shouldn't block the booking confirmation to set it up. Instead, it publishes a "reservation confirmed" message to the queue, and a reminder worker picks it up and schedules the SMS/email notifications. See [Async Processing](concepts.md#15-async-processing-and-background-jobs).

---

### Scheduler (Cron Jobs)
**What it is:** A background process that runs tasks on a schedule (e.g., "every night at midnight").

**Why it's used here:**
- **Mark no-shows**: At some point after the reservation time, if the guest never arrived, the reservation is marked as a no-show and the table is released back to availability.
- **Promote waitlist entries**: When a cancellation happens (or a no-show is marked), the scheduler checks the waitlist for that time slot and notifies the next person in line.

---

## Data Flow

**Searching for a table:**
1. Guest enters criteria (location, date, time, party size) → server queries Elasticsearch for matching restaurants
2. For each matching restaurant, server checks Redis for available slot counts → returns results instantly

**Booking a table:**
3. Guest selects a slot → server acquires a Redis distributed lock for that slot
4. Server opens a PostgreSQL transaction → `SELECT FOR UPDATE` on the time slot row → confirms slot is available → creates reservation record → decrements available count
5. Transaction commits → Redis lock released → Redis availability cache updated
6. Reservation confirmed → "reservation created" message published to queue → reminder worker schedules future SMS/email

**Cancellation:**
7. Guest cancels → PostgreSQL marks reservation as cancelled → Redis availability count incremented → scheduler checks waitlist and notifies next guest if applicable

---

## Interesting Engineering Challenges

- **Double-booking under high concurrency**: Two guests clicking "Book" at the exact same millisecond for the last available table. The combination of a Redis distributed lock (fast outer guard) and PostgreSQL's `SELECT FOR UPDATE` (database-level lock) provides two layers of protection.
- **Cache consistency under high write throughput**: During a popular restaurant's opening week, dozens of bookings and cancellations per minute hit the availability cache. Cache updates must be atomic and consistent so the displayed availability always reflects reality.
- **Waitlist promotion fairness**: When a slot opens, the system should notify the first person on the waitlist and give them a window (e.g., 15 minutes) to confirm before moving to the next person — this requires careful state management.
