# System Design Document — Incident Management System

## Phase 1: Problem Understanding

An Incident Management System for a distributed stack (APIs, MCP Hosts, Distributed Caches, Async Queues, RDBMS, NoSQL) must solve four distinct problems simultaneously:

1. **Ingestion at scale**: Distributed systems produce error signals in bursts — 10k/sec during an outage is not unusual. The system must absorb this without applying back-pressure to the already-degraded services producing the signals.

2. **Deduplication**: An RDBMS outage may cause 50 services to independently report the same root failure. Creating 50 separate "work items" would bury the on-call engineer. We need exactly one work item per failure event.

3. **Workflow enforcement**: Incidents must go through a structured lifecycle (OPEN → INVESTIGATING → RESOLVED → CLOSED). Moving to CLOSED without a Root Cause Analysis must be actively prevented, not just documented as a guideline.

4. **Real-time visibility**: The on-call team needs to see the current state of all active incidents without the UI polling the database on every refresh — that would kill the DB during an outage.

---

## Phase 2: Failure Scenarios & System Responses

### F1: PostgreSQL is slow or down

**Problem**: If signal ingestion synchronously writes to PG, a slow DB means slow API responses. Services try to report failures, can't, give up, and we lose the incident record.

**Solution**: The ingestion API never touches PostgreSQL. It pushes to a Redis Stream and returns `202 Accepted`. The Stream is the write buffer. The background worker processes from the Stream with retries. PostgreSQL only needs to handle worker write throughput, not raw ingest throughput.

### F2: Signal burst (10k/sec)

**Problem**: A major outage causes a spike. Even if PG is healthy, we can't write 10k rows/sec to it.

**Solution**: Redis XADD is O(log N) and handles 500k+ ops/sec. The Stream absorbs the burst. Worker processes at sustainable PG write speed (~1k/sec). `MAXLEN ~100k` prevents unbounded memory growth, dropping oldest messages if truly overwhelmed — acceptable since deduplication means each unique component creates only one work item.

### F3: Redis is down

**Problem**: The ingestion buffer is gone.

**Solution**: The API returns `503 Service Unavailable` with `Retry-After`. No silent data loss. Callers (monitoring agents) are expected to retry. This is the one scenario where the system explicitly tells callers to back off.

### F4: MongoDB is slow

**Problem**: Raw signal storage is an audit log — important but not critical to incident tracking.

**Solution**: MongoDB writes happen after the PostgreSQL work item is confirmed. If Mongo fails, the work item still exists. The MongoDB write is retried independently. The system continues functioning with reduced audit capability.

### F5: Worker crashes mid-processing

**Problem**: A message was delivered to the worker but not ACK'd before the crash.

**Solution**: Redis Streams consumer groups maintain a Pending Entry List (PEL). On restart, the worker calls `XCLAIM` to reclaim un-ACK'd messages and re-processes them. PostgreSQL upsert semantics (or the dedup check) ensure re-processing is idempotent.

---

## Phase 3: Data Modeling Decisions

### PostgreSQL — Work Items & RCA

**Why here?**
- State transitions (OPEN→CLOSED) require ACID guarantees
- The RCA-required-for-CLOSED constraint needs a single source of truth
- MTTR calculation requires consistent timestamps

```sql
work_items:
  id            UUID PRIMARY KEY
  component_id  VARCHAR(255) INDEX    -- dedup queries
  component_type ENUM
  title         VARCHAR(500)
  severity      ENUM(P0-P4)
  status        ENUM(OPEN/INVESTIGATING/RESOLVED/CLOSED)
  signal_count  INTEGER
  created_at    TIMESTAMPTZ           -- incident start time
  resolved_at   TIMESTAMPTZ           -- end time for MTTR
  mttr_minutes  FLOAT                 -- auto-computed

rcas:
  id                    UUID PK
  work_item_id          UUID FK UNIQUE  -- one RCA per work item
  incident_start        TIMESTAMPTZ
  incident_end          TIMESTAMPTZ
  root_cause_category   VARCHAR
  root_cause_detail     TEXT            -- min 20 chars
  fix_applied           TEXT            -- min 10 chars
  prevention_steps      TEXT            -- min 10 chars
  mttr_minutes          FLOAT
```

Compound indexes:
- `(status, severity)` → dashboard filter queries
- `(component_id, status)` → dedup fallback queries

### MongoDB — Raw Signals

**Why here?**
- High write throughput (10k/sec needs horizontal write scaling)
- Schemaless (payload varies by component type)
- Time-series query pattern: "show me all signals for work_item X sorted by time"
- TTL index auto-expires signals after 30 days (data retention policy)

```json
{
  "work_item_id": "uuid",
  "component_id": "RDBMS_CLUSTER_01",
  "signal_type": "error",
  "severity": "P0",
  "message": "Connection pool exhausted",
  "payload": { "connections": 100, "queue": 450 },
  "timestamp": ISODate,
  "processed_at": ISODate
}
```

Indexes:
- `component_id` (queries: "all signals for this component")
- `work_item_id` (queries: "all signals for this incident")
- `(component_id, timestamp DESC)` (time-range queries per component)
- TTL on `timestamp` (30 days)

### Redis — Hot Path Cache

Three key spaces:
1. `dedup:{component_id}` → `work_item_id` (10s TTL)
2. `dashboard:active_incidents` → JSON blob (30s TTL, rebuilt on state change)
3. `rate:{ip}` → sorted set of request timestamps (sliding window)

**Why cache the dashboard?**
During an outage, the dashboard refreshes every few seconds across dozens of browser tabs from the on-call team. Without a cache, each refresh hits PostgreSQL with a join query — exactly when PG is under the most stress. Redis serves the cached response in <1ms.

---

## Phase 4: Design Patterns

### State Pattern

**Problem**: Work item lifecycle rules are complex:
- OPEN can only go to INVESTIGATING
- RESOLVED can go to CLOSED (if RCA) or back to INVESTIGATING (regression)
- CLOSED requires RCA — this is a hard constraint

**Why State Pattern?**
Without it, this logic lives as if/elif chains in multiple service methods. Adding a new status (e.g., "ESCALATED") requires hunting down and modifying every place that checks status. The State Pattern localises each state's rules in one place.

```python
class ResolvedState(WorkItemState):
    def allowed_transitions(self) -> set[WorkItemStatus]:
        return {WorkItemStatus.CLOSED, WorkItemStatus.INVESTIGATING}
    
    def transition_to(self, new_status, has_rca=False):
        if new_status == CLOSED and not has_rca:
            raise ValueError("RCA required")
```

### Strategy Pattern

**Problem**: RDBMS failure = wake someone up at 3am via PagerDuty. Cache degradation = send a Slack message. This mapping needs to be configurable and swappable.

**Why Strategy Pattern?**
It separates "what to alert about" from "how to alert". Adding a new alert channel (e.g., OpsGenie) requires adding one class and one mapping entry — not modifying existing alerting code.

```python
# Runtime strategy selection
strategy = get_alert_strategy(final_severity, is_new_incident=True)
await strategy.send_alert(ctx)
# ^ No if/else. The right implementation is called polymorphically.
```

---

## Phase 5: Concurrency Model

The system uses Python's asyncio cooperative multitasking:

- **Single worker task** runs in the same event loop as FastAPI
- **No threads**: All I/O (Redis, PG, MongoDB) uses async drivers (aioredis, asyncpg, motor)
- **Batch processing**: Worker reads 50 messages at a time, processes them with `asyncio.gather()` — concurrent but not parallel (no GIL issues)
- **No shared mutable state**: Each DB operation uses its own session; Redis operations are atomic

For true parallelism at scale: run multiple worker processes behind a Redis consumer group. Redis ensures each message goes to exactly one consumer.

---

## Phase 6: API Security

| Mechanism | Implementation | Why |
|-----------|---------------|-----|
| API Key | `X-API-Key` header on `/api/v1/signals` | Prevent unauthorized signal injection |
| Rate Limiting | Redis sliding window, 600 req/min/IP | Protect against flood attacks |
| CORS | Whitelist of allowed origins | Browser XSS protection |
| Input Validation | Pydantic v2 strict mode | Reject malformed payloads |
| Non-root container | `USER ims` in Dockerfile | Container escape mitigation |
| Parameterized queries | SQLAlchemy ORM (no raw SQL) | SQL injection prevention |

---

## What I Would Add With More Time

1. **Kafka instead of Redis Streams** — better replay semantics, partition-based parallelism
2. **JWT authentication** — per-user permissions (viewer vs. responder vs. admin)
3. **Prometheus metrics** — expose `/metrics` endpoint for Grafana dashboards
4. **K8s Helm chart** — production deployment with HPA on worker pods
5. **Webhook integrations** — real PagerDuty/Slack API calls
6. **Multi-tenancy** — org-level isolation for SaaS use case
