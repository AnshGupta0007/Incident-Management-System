# Prompt Used to Build This System

This file documents the prompt and specification used to generate this repository, as required by the submission guidelines ("All markdowns and prompts used to create this repository should be checked in").

## Assignment Specification

The assignment asked for a production-grade Incident Management System with:

- **Ingestion**: High-throughput signal ingestion (up to 10k/sec), async processing
- **Deduplication**: 10-second window — 100 signals for the same component_id → 1 work item
- **Storage**: Separate stores for raw signals (NoSQL), work items (RDBMS), and hot-path cache
- **Workflow**: State machine (OPEN → INVESTIGATING → RESOLVED → CLOSED), mandatory RCA before CLOSED
- **Alerting**: Strategy Pattern — different alert types per component type (P0 for RDBMS, P2 for Cache)
- **MTTR**: Auto-calculated from first signal to RCA end time
- **Frontend**: React dashboard with live feed, incident detail, RCA form
- **Infrastructure**: Docker Compose, all services containerized
- **Resilience**: Retry logic, rate limiting, /health endpoint, throughput metrics

## Engineering Prompt Used

The AI was prompted to behave as a Principal SRE / Distributed Systems Architect and to:
1. Think deeply before coding (system challenges, failure scenarios, non-functional requirements)
2. Design the architecture with explicit justification for each technology choice
3. Implement design patterns correctly (State, Strategy) with explanations of *why* each was used
4. Handle backpressure as a first-class concern
5. Write production-ready code with proper error handling, retries, and observability

## Architecture Decisions Made

All technology choices and their tradeoffs are documented in `README.md` and `docs/SYSTEM_DESIGN.md`.

Key decisions:
- Redis Streams over Kafka (operational simplicity for demo; same guarantees at smaller scale)
- PostgreSQL over MongoDB for work items (ACID needed for state transitions)
- FastAPI over Go/Express (async-first, Python's rapid iteration advantage)
- Separate MongoDB for signals (10k/sec write throughput requirement, flexible schema)
- Two-tier deduplication (Redis fast-path + PostgreSQL fallback for crash resilience)
