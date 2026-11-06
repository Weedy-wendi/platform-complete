"""Load test for the Pingce MCP server.

The default profile is 50 QPS for 30 minutes (SC-010). The script reports
latency percentiles, 429/5xx counts, and the server's process memory growth
read from ``/metrics`` (``process_resident_memory_bytes``). It exits non-zero
when a configured threshold is exceeded.

Use a dedicated load-test API key whose rate limit is raised for the run;
otherwise 429 responses are counted separately from 5xx errors.

Examples:
    python scripts/load-mcp.py --url http://127.0.0.1:8765/mcp --api-key "$env:PINGCE_LOAD_KEY"
    python scripts/load-mcp.py --url http://127.0.0.1:8765/mcp --api-key "$env:PINGCE_LOAD_KEY" --qps 5 --duration 10
    python scripts/load-mcp.py ... --metrics-url http://127.0.0.1:8765/metrics --max-p95-ms 300 --max-memory-growth-pct 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse, urlunparse

import httpx


@dataclass
class Stats:
    latencies_ms: list[float] = field(default_factory=list)
    server_errors: int = 0
    rate_limited: int = 0
    other_errors: int = 0
    responses: int = 0


async def _worker(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict,
    stats: Stats,
    stop_at: float,
) -> None:
    while time.monotonic() < stop_at:
        started = time.perf_counter()
        try:
            response = await client.post(url, json=payload, headers=headers, timeout=30.0)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            stats.responses += 1
            if response.status_code >= 500:
                stats.server_errors += 1
            elif response.status_code == 429:
                stats.rate_limited += 1
            elif response.status_code >= 400:
                stats.other_errors += 1
            else:
                stats.latencies_ms.append(elapsed_ms)
        except Exception:
            stats.other_errors += 1
        await asyncio.sleep(max(0.0, 1.0 - (time.perf_counter() - started)))


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _default_metrics_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path
    if path.endswith("/mcp"):
        path = path[: -len("/mcp")] + "/metrics"
    else:
        path = "/metrics"
    return urlunparse(parsed._replace(path=path, params="", query="", fragment=""))


def _parse_memory(text: str) -> float | None:
    for line in text.splitlines():
        if line.startswith("process_resident_memory_bytes"):
            try:
                return float(line.split()[-1])
            except (IndexError, ValueError):
                return None
    return None


async def _fetch_memory(client: httpx.AsyncClient, metrics_url: str) -> float | None:
    try:
        response = await client.get(metrics_url, timeout=5.0)
        if response.status_code != 200:
            return None
        return _parse_memory(response.text)
    except Exception:
        return None


async def run(args: argparse.Namespace) -> int:
    headers = {
        "Authorization": f"Bearer {args.api_key}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": args.tool, "arguments": json.loads(args.arguments)},
    }
    stats = Stats()
    stop_at = time.monotonic() + args.duration
    metrics_url = args.metrics_url or _default_metrics_url(args.url)
    async with httpx.AsyncClient(http2=False) as client:
        memory_start = await _fetch_memory(client, metrics_url)
        await asyncio.gather(
            *[_worker(client, args.url, headers, payload, stats, stop_at) for _ in range(args.qps)]
        )
        memory_end = await _fetch_memory(client, metrics_url)

    total = stats.responses + stats.other_errors
    p50 = _percentile(stats.latencies_ms, 0.50)
    p95 = _percentile(stats.latencies_ms, 0.95)
    p99 = _percentile(stats.latencies_ms, 0.99)
    mean = statistics.mean(stats.latencies_ms) if stats.latencies_ms else 0.0

    print(f"requests:       {total}")
    print(f"2xx:            {len(stats.latencies_ms)}")
    print(f"429:            {stats.rate_limited}")
    print(f"4xx (other):    {stats.other_errors}")
    print(f"5xx:            {stats.server_errors}")
    print(f"P50:            {p50:.1f} ms")
    print(f"P95:            {p95:.1f} ms")
    print(f"P99:            {p99:.1f} ms")
    print(f"mean:           {mean:.1f} ms")

    memory_growth_pct: float | None = None
    if memory_start is not None and memory_end is not None and memory_start > 0:
        memory_growth_pct = (memory_end - memory_start) / memory_start * 100.0
        print(f"memory start:   {memory_start / (1024 * 1024):.1f} MiB")
        print(f"memory end:     {memory_end / (1024 * 1024):.1f} MiB")
        print(f"memory growth:  {memory_growth_pct:.2f}%")
    else:
        print("memory:         not available (no process_resident_memory_bytes)")

    failures: list[str] = []
    if stats.server_errors:
        failures.append(f"5xx errors: {stats.server_errors}")
    if args.max_p95_ms > 0 and stats.latencies_ms and p95 > args.max_p95_ms:
        failures.append(f"P95 {p95:.1f}ms > {args.max_p95_ms:.1f}ms")
    if (
        args.max_memory_growth_pct >= 0
        and memory_growth_pct is not None
        and memory_growth_pct > args.max_memory_growth_pct
    ):
        failures.append(f"memory growth {memory_growth_pct:.2f}% > {args.max_memory_growth_pct:.2f}%")

    if failures:
        print("FAIL: " + "; ".join(failures))
        return 1
    print("PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Load test the Pingce MCP server")
    parser.add_argument("--url", default="http://127.0.0.1:8765/mcp")
    parser.add_argument("--api-key", required=True)
    parser.add_argument("--tool", default="list_projects")
    parser.add_argument("--arguments", default="{}")
    parser.add_argument("--qps", type=int, default=50)
    parser.add_argument("--duration", type=int, default=1800, help="seconds (default 30 min)")
    parser.add_argument("--metrics-url", default=None, help="defaults to the /metrics endpoint next to --url")
    parser.add_argument("--max-p95-ms", type=float, default=1000.0, help="0 disables the P95 check")
    parser.add_argument(
        "--max-memory-growth-pct",
        type=float,
        default=10.0,
        help="negative disables the memory-growth check",
    )
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
