# Job Board & Applicant Tracking System

> **New to web apps?** Read [concepts.md](concepts.md) first — it explains databases, caches, message queues, and other building blocks used throughout this document.

## Overview
A two-sided marketplace connecting job seekers and employers. Companies post job listings, candidates apply, and recruiters manage their hiring pipeline (sometimes called an **ATS — Applicant Tracking System**) to move candidates through stages: applied → phone screen → interview → offer → hired or rejected.

This app is a good example of a system with two very different user types (candidates vs. recruiters) and two different workloads: **search** (candidates browsing and filtering listings) and **workflow management** (recruiters updating application states and communicating with candidates).

## Key Features
- Job listing creation and management
- Candidate profiles and resume upload
- Job search with filters (location, salary, remote, skills)
- Application submission and status tracking
- Recruiter pipeline (stages: applied → screen → interview → offer → hired/rejected)
- Email notifications on status changes
- Job recommendations for candidates

---

## Infrastructure

### Primary Database — PostgreSQL
**What it is:** A relational database that stores structured data in tables with rows and columns. See [Relational Databases](concepts.md#3-relational-databases-sql).

**Why it's used here:** Job listings, candidates, and applications are naturally relational — a candidate applies to many jobs, a job receives applications from many candidates, a recruiter manages many applications. PostgreSQL's relational model handles these **many-to-many relationships** cleanly.

**What it stores:**
- `companies` — employer profiles, logos, descriptions
- `jobs` — title, description, salary range, location, required skills, expiry date
- `candidates` — profiles, contact info, skills
- `applications` — which candidate applied to which job, and the current pipeline stage
- `pipeline_stages` — the ordered stages each application moves through
- `interviews` — scheduled interview records tied to an application

---

### Cache — Redis
**What it is:** A fast in-memory store used here for caching frequently read data and enforcing limits. See [The Cache](concepts.md#5-the-cache).

**How it's used:**

- **Job listing cache**: Popular listings (high-traffic job postings from well-known companies) are cached in Redis so repeated requests don't all hit PostgreSQL. When a listing is updated, its cache entry is invalidated immediately.

- **Search result cache**: Common searches like "software engineer, remote" are run by thousands of candidates daily. The Elasticsearch results for these queries are cached in Redis for 5 minutes. This reduces load on Elasticsearch without any noticeable staleness to users (job listings don't change by the second).

- **Session storage**: Both recruiter and candidate sessions are stored in Redis with TTL-based expiry. See [Sessions and Authentication](concepts.md#11-sessions-and-authentication) and [TTL](concepts.md#14-ttl-time-to-live).

- **Rate limiting**: To prevent spam applications, a candidate is limited to (for example) 50 applications per day. Redis counters track this per candidate ID. See [Rate Limiting](concepts.md#12-rate-limiting).

---

### Search — Elasticsearch
**What it is:** A dedicated search engine for full-text and filtered queries. See [Search Engines](concepts.md#8-search-engines).

**Why it's used here:** Job searching involves complex, multi-dimensional queries that are slow in a regular database:
- "Show me software engineering jobs within 25 miles of Seattle that pay at least $120k and allow remote work"
- "Show me candidates with Python and machine learning experience for this role"

These combine full-text matching (job descriptions, skill tags), geographic distance, numeric range filtering (salary), and relevance ranking — all in under a second. Elasticsearch handles all of this natively.

**Two directions of search:**
- **Candidate → jobs**: candidates search for listings matching their criteria
- **Recruiter → candidates**: recruiters search for candidates whose profiles match a role's requirements

---

### Object Storage — Azure Blob Storage (production) / Azurite (local)
**What it is:** A service for storing and retrieving large files by URL. See [Object Storage](concepts.md#7-object-storage).

**Why it's used here:** Resumes are PDF or DOCX files — too large and too binary to store in PostgreSQL. Candidates upload their resume to Azure Blob, and the database stores just the blob path. Recruiters download it via a temporary SAS (Shared Access Signature) URL (a URL that grants one-time access and expires after a short time, protecting the file from unauthorized access).

Company logos are handled the same way.

**Running locally:** Use [Azurite](https://learn.microsoft.com/azure/storage/common/storage-use-azurite) — Microsoft's official Azure Blob emulator that runs in Docker and supports the same SAS URL flow as production Azure Blob Storage. No Azure account needed.

---

### Background Job Queue — Sidekiq / BullMQ
**What it is:** A system for running slow or scheduled tasks outside the main request cycle. See [The Message Queue](concepts.md#6-the-message-queue) and [Async Processing](concepts.md#15-async-processing-and-background-jobs).

**Why it's used here:** Several tasks must happen in response to events but don't need to block the response:

- **Status-change emails**: When a recruiter moves a candidate from "phone screen" to "interview", the candidate should receive an email. Sending an email involves calling an external email service — slow and potentially unreliable. The server queues the email task immediately and returns a response; the worker sends the email seconds later.

- **Listing expiry**: Every night, a scheduled job scans for job listings past their expiry date and marks them as inactive. This is a **cron job** — a task that runs on a schedule (e.g., every night at 2 AM).

- **Recommendation scoring**: Computing job recommendations for a candidate is computationally expensive. It runs nightly for all candidates and stores the results. When a candidate logs in the next morning, their recommendations are already ready.

---

### Recommendation Engine (optional)
**What it is:** A system that matches candidates to relevant job listings using their skills and history.

**How it works (simplified):** The engine compares each candidate's skill tags against each job's required skill tags and computes a similarity score. More sophisticated versions use machine learning (embedding vectors) to understand that "Python developer" and "Django engineer" are related even if the exact words don't match. Top-N recommendations per candidate are pre-computed overnight and stored in Redis or PostgreSQL.

**Why pre-compute instead of computing live?** Running similarity matching across thousands of jobs for each candidate in real time would be too slow. Nightly batch processing computes everything ahead of time so recommendations load instantly.

---

## Data Flow

**Candidate searches for a job:**
1. Candidate enters search query → server checks Redis cache for this query → cache hit: return immediately
2. Cache miss → Elasticsearch runs full-text + geo-distance query → result cached in Redis for 5 minutes → returned to browser

**Candidate applies:**
3. Candidate submits application → PostgreSQL insert into `applications` with status "applied"
4. Job published to background queue → worker sends confirmation email to candidate asynchronously

**Recruiter advances a candidate:**
5. Recruiter changes stage from "phone screen" to "interview" → PostgreSQL update
6. Stage change queued as background job → worker sends notification email to candidate

**Nightly batch:**
7. Scheduler triggers job expiry scan → expired listings marked inactive in PostgreSQL
8. Recommendation engine re-scores candidate-job matches → stores top-N recommendations per candidate in Redis

---

## Interesting Engineering Challenges

- **Resume parsing**: To power skills-based search, the system needs to extract structured skills from an uploaded PDF resume (e.g., detect "Python", "Azure", "SQL"). This requires natural language processing — a non-trivial pipeline that runs as a background job after each resume upload.
- **Multi-dimensional ranking**: A job search result should rank listings by a combination of recency (newer is better), relevance (keyword match), and candidate fit (skills overlap). Balancing these three signals to produce a natural-feeling ranking is an ongoing tuning problem.
- **Preventing spam applications**: Rate limiting by candidate prevents bulk submissions. Duplicate detection (same candidate applying to the same job twice) needs to be enforced at the database level with a unique constraint on `(candidate_id, job_id)` in the `applications` table.
