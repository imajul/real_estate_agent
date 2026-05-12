import httpx
import time
import random
from abc import ABC, abstractmethod
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from models import Property


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}


class BaseScraper(ABC):
    def __init__(self, timeout: int = 30, min_delay: float = 1.5, max_delay: float = 3.5):
        self.timeout = timeout
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.client = httpx.Client(
            headers=HEADERS,
            timeout=timeout,
            follow_redirects=True,
        )

    def _sleep(self):
        time.sleep(random.uniform(self.min_delay, self.max_delay))

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=15),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
    )
    def _get(self, url: str, **kwargs) -> httpx.Response:
        self._sleep()
        response = self.client.get(url, **kwargs)
        response.raise_for_status()
        return response

    @abstractmethod
    def search(self, neighborhood: str, max_results: int = 50) -> list[Property]:
        """Search properties in a neighborhood."""
        ...

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.client.close()
