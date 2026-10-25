import asyncio
import json
import socket
import subprocess
import sys
from collections.abc import Generator
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from scrapy import Request
from scrapy.exceptions import DownloadTimeoutError
from scrapy.http import HtmlResponse, Response
from scrapy.utils.test import get_crawler
from twisted.internet.error import DNSLookupError, TCPTimedOutError, TimeoutError
from twisted.python.failure import Failure

from jg.plucker.items import JobLogo
from jg.plucker.job_logos.spider import Spider
from jg.plucker.scrapers import StatsError


PROJECT_DIR = Path(__file__).parent.parent.parent

CRAWL_SCRIPT = """
import json, sys
from scrapy import signals
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from jg.plucker.job_logos.spider import Spider

settings = get_project_settings()
settings.setdict({"HTTPCACHE_ENABLED": False, "FEEDS": {}}, priority="cmdline")
# Spider settings have priority over project settings, so patch them
Spider.custom_settings = (Spider.custom_settings or {}) | {"DOWNLOAD_TIMEOUT": 1}
items = []
process = CrawlerProcess(settings, install_root_handler=False)
crawler = process.create_crawler(Spider)
crawler.signals.connect(lambda item: items.append(item), signal=signals.item_scraped)
process.crawl(crawler, links=[{"url": sys.argv[1]}])
process.start()
stats = crawler.stats.get_stats()
print(json.dumps({"stats": {k: v for k, v in stats.items() if isinstance(v, int)},
                  "items_count": len(items)}))
"""


@pytest.fixture
def unresponsive_url() -> Generator[str]:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen()  # accepts connections, never responds
        yield f"http://127.0.0.1:{server.getsockname()[1]}/"


@pytest.fixture
def refusing_url() -> str:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        port = server.getsockname()[1]
    return f"http://127.0.0.1:{port}/"  # nothing listens there anymore


def crawl(url: str) -> dict[str, Any]:
    process = subprocess.run(
        [sys.executable, "-c", CRAWL_SCRIPT, url],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    return json.loads(process.stdout.splitlines()[-1])


@pytest.mark.parametrize(
    "exception", [DownloadTimeoutError, TimeoutError, TCPTimedOutError]
)
def test_spider_on_error_skips_timeouts(caplog, exception: type[Exception]):
    crawler = get_crawler(Spider)
    spider = Spider.from_crawler(crawler, links=[])
    failure = Failure(exception())
    failure.request = type("Request", (), {"url": "https://example.com/"})()

    with caplog.at_level("WARNING"):
        result = spider.on_error(failure)

    assert result is None
    assert caplog.messages == ["Skipping https://example.com/: timed out"]
    assert crawler.stats.get_value("job_logos/timeouts_skipped") == 1


def test_spider_on_error_passes_other_failures():
    spider = Spider(links=[])
    failure = Failure(DNSLookupError())

    assert spider.on_error(failure) is failure


def test_spider_crawl_timeout(unresponsive_url: str):
    result = crawl(unresponsive_url)

    assert result["items_count"] == 0
    assert result["stats"]["job_logos/timeouts_skipped"] == 1
    Spider.evaluate_stats(result["stats"], min_items=0)


def test_spider_crawl_connection_refused(refusing_url: str):
    result = crawl(refusing_url)

    assert result["items_count"] == 0
    with pytest.raises(StatsError, match="Errors logged"):
        Spider.evaluate_stats(result["stats"], min_items=0)


@pytest.mark.parametrize(
    "stats_override",
    [
        {"log_count/ERROR": 1},
        {"log_count/ERROR": 2, "job_logos/timeouts_skipped": 1},
    ],
)
def test_spider_evaluate_stats_counts_other_errors(stats_override: dict):
    with pytest.raises(StatsError, match="Errors logged"):
        Spider.evaluate_stats({"item_scraped_count": 1} | stats_override, min_items=1)


def test_spider_evaluate_stats_tolerates_timeouts():
    Spider.evaluate_stats(
        {
            "item_scraped_count": 1,
            "log_count/ERROR": 2,
            "job_logos/timeouts_skipped": 2,
        },
        min_items=1,
    )


def test_spider_start_keeps_input_urls_as_given():
    urls = ["https://example.com", "https://example.com/logo.png"]
    spider = Spider(links=[{"url": url} for url in urls])

    async def collect():
        return [request async for request in spider.start()]

    requests = asyncio.run(collect())

    assert [request.cb_kwargs["source_url"] for request in requests] == urls


def test_spider_parse_keeps_source_url_after_redirect():
    source_url = "https://example.com"
    response = HtmlResponse(
        "https://example.com/en/",
        body=b'<html><head><link rel="icon" href="/icon.png"></head></html>',
        request=Request("https://example.com/en/"),
    )
    requests = list(Spider().parse(response, source_url=source_url))

    assert {request.url for request in requests} == {
        "https://example.com/favicon.ico",
        "https://example.com/icon.png",
    }
    assert all(request.cb_kwargs["source_url"] == source_url for request in requests)


def test_spider_parse_image_keeps_source_url_after_redirect():
    source_url = "https://example.com"
    buffer = BytesIO()
    Image.new("RGB", (16, 16)).save(buffer, format="PNG")
    response = Response(
        "https://example.com/favicon.ico",
        headers={"Content-Type": "image/png"},
        body=buffer.getvalue(),
        request=Request("https://example.com/favicon.ico"),
    )
    items = list(Spider().parse(response, source_url=source_url))

    assert len(items) == 1
    assert isinstance(items[0], JobLogo)
    assert items[0]["source_url"] == source_url
