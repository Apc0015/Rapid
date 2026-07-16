"""Single-purpose schedule dispatcher for production deployments."""
from __future__ import annotations

import asyncio
import logging
import os

from infrastructure.integration_hub import get_integration_hub


async def run() -> None:
    interval = max(30, int(os.getenv("RAPID_SCHEDULER_INTERVAL_SECONDS", "60")))
    while True:
        try:
            results = get_integration_hub().dispatch_due_schedules()
            if results:
                logging.getLogger(__name__).info("Dispatched %s scheduled workflow(s)", len(results))
        except Exception:
            logging.getLogger(__name__).exception("Scheduled workflow dispatch failed")
        await asyncio.sleep(interval)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
