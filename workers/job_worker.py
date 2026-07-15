"""Standalone durable job worker used by container and cloud deployments."""
from __future__ import annotations

import asyncio
import logging

from infrastructure.job_handlers import register_default_job_handlers
from infrastructure.job_queue import run_worker


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    register_default_job_handlers()
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
