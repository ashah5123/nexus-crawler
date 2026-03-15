from __future__ import annotations

import asyncio
import logging
import os
import signal
import socket

from dotenv import load_dotenv

from orchestrator.state import StateManager
from shared.queue import TaskQueue
from shared.models import WorkerInfo
from worker.rate_limiter import DomainRateLimiter
from worker.scraper import Scraper

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, worker_id: str, redis_url: str, concurrency: int):
        self.queue = TaskQueue(redis_url)
        self.scraper = Scraper(DomainRateLimiter(default_delay=1.0))
        self.state = StateManager(self.queue)
        self.info = WorkerInfo(
            id=worker_id,
            hostname=socket.gethostname(),
            status="idle",
        )
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.running = False
        self.active_tasks = 0

    async def start(self) -> None:
        self.running = True
        self.queue.register_worker(self.info)
        logger.info("Worker %s started, concurrency=%s", self.info.id, self.concurrency)
        await asyncio.gather(self.heartbeat_loop(), self.main_loop())

    async def heartbeat_loop(self) -> None:
        while self.running:
            self.queue.update_worker_heartbeat(self.info.id)
            self.info.status = "busy" if self.active_tasks > 0 else "idle"
            self.queue.register_worker(self.info)
            await asyncio.sleep(10)

    async def main_loop(self) -> None:
        while self.running:
            task = self.queue.pop_task(timeout=2)
            if task:
                asyncio.create_task(self.process_task(task))
            else:
                await asyncio.sleep(0.1)

    async def process_task(self, task) -> None:
        async with self.semaphore:
            self.active_tasks += 1
            try:
                self.state.start_task(task)
                result = await self.scraper.scrape(task)
                self.state.complete_task(task, result)
                logger.info("✅ Scraped %s in %.0fms", task.url, result.response_time_ms)
            except Exception as e:
                self.state.fail_task(task, str(e))
                logger.error("❌ Failed %s: %s", task.url, e)
            finally:
                self.active_tasks -= 1

    async def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        self.info.status = "offline"
        self.queue.register_worker(self.info)
        try:
            await self.scraper.close()
        except Exception:
            logger.exception("Error while closing scraper")
        logger.info("Worker stopped")


def main() -> None:
    load_dotenv()

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    worker_id = os.getenv("WORKER_ID", f"worker-{socket.gethostname()}")
    concurrency = int(os.getenv("WORKER_CONCURRENCY", "4"))

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    worker = Worker(worker_id, redis_url, concurrency)

    async def runner() -> None:
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(
                signal.SIGINT, lambda: asyncio.create_task(worker.stop())
            )
            loop.add_signal_handler(
                signal.SIGTERM, lambda: asyncio.create_task(worker.stop())
            )
        except NotImplementedError:
            # Some platforms/event loops may not support signal handlers.
            pass

        await worker.start()

    asyncio.run(runner())


if __name__ == "__main__":
    main()
