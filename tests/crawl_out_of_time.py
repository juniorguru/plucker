"""Crawls a local server slower than CLOSESPIDER_TIMEOUT allows and prints stats as JSON

Runs in a subprocess, because the Twisted reactor can't be restarted.
Usage: python crawl_out_of_time.py
"""

import json
import threading
import time
from collections.abc import AsyncGenerator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scrapy import Request, Spider
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from twisted.python.failure import Failure


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args) -> None:
        pass


class SlowSpider(Spider):
    name = "slow"

    custom_settings = {
        "AUTOTHROTTLE_ENABLED": False,
        "DOWNLOAD_DELAY": 1,
        "RANDOMIZE_DOWNLOAD_DELAY": False,
        "CONCURRENT_REQUESTS": 1000,
        "CLOSESPIDER_TIMEOUT": 2,
    }

    def __init__(self, base_url: str, **kwargs):
        super().__init__(**kwargs)
        self.base_url = base_url
        self.errbacks = []

    async def start(self) -> AsyncGenerator[Request]:
        for i in range(20):
            yield Request(f"{self.base_url}{i}", errback=self.on_error)

    def parse(self, response) -> None:
        pass

    def on_error(self, failure: Failure) -> None:
        self.errbacks.append(failure.type.__name__)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{server.server_address[1]}/"

    settings = get_project_settings()
    settings.setdict({"HTTPCACHE_ENABLED": False, "FEEDS": {}}, priority="cmdline")
    process = CrawlerProcess(settings, install_root_handler=False)
    crawler = process.create_crawler(SlowSpider)
    process.crawl(crawler, base_url=base_url)
    started_at = time.monotonic()
    process.start()
    server.shutdown()

    stats = crawler.stats.get_stats()
    print(
        json.dumps(
            {
                "duration": time.monotonic() - started_at,
                "finish_reason": stats["finish_reason"],
                "responses_count": stats.get("response_received_count", 0),
                "errbacks": crawler.spider.errbacks,
            }
        )
    )


if __name__ == "__main__":
    main()
