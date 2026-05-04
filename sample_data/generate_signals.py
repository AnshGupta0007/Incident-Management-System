#!/usr/bin/env python3
"""
Sample Data Generator — Simulates a realistic production cascade failure.

Scenario:
  1. RDBMS_CLUSTER_01 begins throwing connection errors (P0)
  2. API_GATEWAY_01 starts timing out due to DB dependency (P1)
  3. CACHE_CLUSTER_01 gets overwhelmed with fallback reads (P2)
  4. MCP_HOST_01 health checks fail (P1)
  5. ASYNC_QUEUE_01 consumer lag grows (P2)
  6. Recovery signals after 30 seconds

Usage:
  python sample_data/generate_signals.py [--host localhost] [--port 8000] [--count 100]
"""

import argparse
import asyncio
import json
import random
import sys
from datetime import datetime, timezone

import urllib.request
import urllib.error


API_KEY = "ims-ingest-key-2024"

SCENARIO = [
    # (component_id, component_type, signal_type, severity, messages)
    (
        "RDBMS_CLUSTER_01", "RDBMS", "error", "P0",
        [
            "Connection pool exhausted: max_connections=100 reached",
            "Query timeout after 30s: SELECT * FROM users",
            "Deadlock detected on table 'transactions'",
            "Replication lag exceeded 5s on replica-02",
            "WAL disk usage at 98% — checkpoint urgently needed",
        ]
    ),
    (
        "API_GATEWAY_01", "API", "latency", "P1",
        [
            "p99 latency: 4500ms (threshold: 200ms)",
            "Database connection refused: host=RDBMS_CLUSTER_01",
            "Circuit breaker OPEN for service: UserService",
            "HTTP 503 rate: 45% of requests",
        ]
    ),
    (
        "CACHE_CLUSTER_01", "CACHE", "availability", "P2",
        [
            "Cache miss rate spike: 89% (normal: 5%)",
            "Memory eviction rate: 10k/sec",
            "Redis sentinel failover initiated",
        ]
    ),
    (
        "MCP_HOST_01", "MCP_HOST", "error", "P1",
        [
            "Health check failed: /health returned 503",
            "MCP host not responding to heartbeat",
        ]
    ),
    (
        "ASYNC_QUEUE_01", "QUEUE", "saturation", "P2",
        [
            "Consumer group lag: 50,000 messages",
            "Producer throughput exceeds consumer capacity",
            "Dead letter queue growing: 1200 messages",
        ]
    ),
]


def send_signal(host: str, port: int, payload: dict) -> dict:
    url = f"http://{host}:{port}/api/v1/signals"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-API-Key": API_KEY,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"  ERROR {e.code}: {body[:200]}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"  FAILED: {e}", file=sys.stderr)
        return {}


def main():
    parser = argparse.ArgumentParser(description="IMS Sample Data Generator")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--count", default=50, type=int, help="Total signals to send")
    parser.add_argument("--delay", default=0.1, type=float, help="Delay between signals (sec)")
    args = parser.parse_args()

    print(f"🔥 Simulating cascade failure → {args.host}:{args.port}")
    print(f"   Sending {args.count} signals with {args.delay}s delay\n")

    sent = 0
    for i in range(args.count):
        comp_id, comp_type, sig_type, severity, messages = SCENARIO[i % len(SCENARIO)]
        msg = messages[i % len(messages)]

        payload = {
            "component_id": comp_id,
            "component_type": comp_type,
            "signal_type": sig_type,
            "severity": severity,
            "message": msg,
            "payload": {
                "iteration": i,
                "simulated": True,
                "env": "production-sim",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source_host": f"prod-host-{random.randint(1, 10):02d}",
        }

        result = send_signal(args.host, args.port, payload)
        if result.get("accepted"):
            print(f"  [{i+1:3d}/{args.count}] ✓ {comp_id} [{severity}] → stream_id={result.get('stream_id', 'n/a')[:16]}")
            sent += 1
        else:
            print(f"  [{i+1:3d}/{args.count}] ✗ {comp_id} — failed")

        if args.delay > 0:
            import time
            time.sleep(args.delay)

    print(f"\n✅ Done. {sent}/{args.count} signals sent.")
    print(f"   Expected ~{len(SCENARIO)} work items (deduplication should cluster signals).")
    print(f"\n   View dashboard: http://{args.host}:3000")
    print(f"   API docs: http://{args.host}:{args.port}/docs")


if __name__ == "__main__":
    main()
