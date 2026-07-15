"""Authenticated concurrent load smoke test for release validation."""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx


async def run(base_url: str, request_count: int, concurrency: int, p95_limit_ms: float) -> None:
    timeout = httpx.Timeout(20)
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        login = await client.post("/people-ops/demo-session")
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        semaphore = asyncio.Semaphore(concurrency)
        durations: list[float] = []
        failures: list[str] = []
        endpoints = ["/workspace/overview", "/workspace/records", "/workspace/meetings", "/workspace/actions", "/workspace/notifications", "/health/ready"]

        async def one(index: int) -> None:
            async with semaphore:
                started = time.perf_counter()
                try:
                    response = await client.get(endpoints[index % len(endpoints)], headers=headers)
                    if response.status_code >= 400:
                        failures.append(f"{response.status_code}:{endpoints[index % len(endpoints)]}")
                except Exception as error:
                    failures.append(str(error))
                finally:
                    durations.append((time.perf_counter() - started) * 1000)

        await asyncio.gather(*(one(index) for index in range(request_count)))
    ordered = sorted(durations)
    p50 = statistics.median(ordered)
    p95 = ordered[max(0, int(len(ordered) * 0.95) - 1)]
    print({"requests": request_count, "concurrency": concurrency, "failures": len(failures), "p50_ms": round(p50, 2), "p95_ms": round(p95, 2), "max_ms": round(max(ordered), 2)})
    if failures:
        raise SystemExit(f"Load smoke failed: {failures[:5]}")
    if p95 > p95_limit_ms:
        raise SystemExit(f"Load smoke p95 {p95:.2f}ms exceeded {p95_limit_ms:.2f}ms")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--p95-limit-ms", type=float, default=1500)
    args = parser.parse_args()
    asyncio.run(run(args.base_url.rstrip("/"), max(1, args.requests), max(1, args.concurrency), args.p95_limit_ms))
