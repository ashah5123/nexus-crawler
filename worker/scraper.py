import time
import logging
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from shared.models import ScrapeTask, ScrapeResult
from worker.rate_limiter import DomainRateLimiter

logger = logging.getLogger(__name__)


class Scraper:
    def __init__(self, rate_limiter: DomainRateLimiter, timeout: int = 30):
        self.rate_limiter = rate_limiter
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            headers={"User-Agent": "NexusCrawler/1.0"},
            follow_redirects=True,
            max_redirects=5,
            verify=False,
        )

    async def scrape(self, task: ScrapeTask) -> ScrapeResult:
        await self.rate_limiter.wait(task.domain)
        start = time.monotonic()
        response = await self.client.get(task.url)
        response_time_ms = (time.monotonic() - start) * 1000

        soup = BeautifulSoup(response.text, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None
        text_content = soup.get_text(separator=" ", strip=True)[:5000]
        links = list({
            urljoin(task.url, a["href"])
            for a in soup.find_all("a", href=True)
            if urljoin(task.url, a["href"]).startswith("http")
        })[:100]

        return ScrapeResult(
            url=task.url,
            title=title,
            text_content=text_content,
            links=links,
            status_code=response.status_code,
            response_time_ms=response_time_ms,
        )

    async def close(self):
        await self.client.aclose()
