from __future__ import annotations

import logging
import os

import uvicorn
from dotenv import load_dotenv

from orchestrator.api import app


def main() -> None:
    load_dotenv()

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    _ = redis_url  # read for parity with service config

    host = os.getenv("HOST", "0.0.0.0")
    port = os.getenv("PORT", "8000")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    uvicorn.run(app, host=host, port=int(port), log_level="info")


if __name__ == "__main__":
    main()

