import asyncio
import json
import socket
import subprocess
import sys
import threading
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from apify_client import ApifyClientAsync
from apify_client.errors import ApifyClientError
from PIL import Image
from scrapy import Request
from scrapy.exceptions import DownloadTimeoutError
from scrapy.http import HtmlResponse, Response
from scrapy.utils.test import get_crawler
from twisted.internet.error import DNSLookupError, TCPTimedOutError, TimeoutError
from twisted.python.failure import Failure

from jg.plucker.items import JobLogo
from jg.plucker.job_logos import spider as spider_module
from jg.plucker.job_logos.spider import Spider, select_reusable_logos
from jg.plucker.scrapers import StatsError


PROJECT_DIR = Path(__file__).parent.parent.parent


class FakeActor:
    apify_client = None
    configuration = SimpleNamespace(actor_id="abc")

    @staticmethod
    def is_at_home() -> bool:
        return False


@pytest.fixture(autouse=True)
def fake_actor(monkeypatch: pytest.MonkeyPatch) -> type[FakeActor]:
    # The real Actor would create and cache the global configuration,
    # which would then leak to other tests
    monkeypatch.setattr(spider_module, "Actor", FakeActor)
    return FakeActor


CRAWL_SCRIPT = Path(__file__).parent / "crawl.py"


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
        [sys.executable, CRAWL_SCRIPT, url],
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


NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)


def logo_item(
    source_url: str, fetched_at: datetime | str | None = None, **kwargs
) -> dict:
    item = {
        "image_url": "https://api.apify.com/v2/key-value-stores/abc/records/123",
        "original_image_url": f"{source_url}/favicon.ico",
        "width": 16,
        "height": 16,
        "format": "png",
        "source_url": source_url,
    }
    if isinstance(fetched_at, datetime):
        item["fetched_at"] = fetched_at.isoformat()
    elif fetched_at:
        item["fetched_at"] = fetched_at
    return item | kwargs


def test_select_reusable_logos():
    items = [
        logo_item("https://a.example.com", NOW - timedelta(days=1)),
        logo_item("https://a.example.com", NOW - timedelta(days=1), width=32),
        logo_item("https://b.example.com", NOW - timedelta(days=1)),
    ]
    logos = select_reusable_logos(items, ["https://a.example.com"], NOW)

    assert list(logos) == ["https://a.example.com"]
    assert [logo["width"] for logo in logos["https://a.example.com"]] == [16, 32]
    assert all(isinstance(logo, JobLogo) for logo in logos["https://a.example.com"])
    assert dict(logos["https://a.example.com"][0]) == items[0]


@pytest.mark.parametrize(
    "item",
    [
        logo_item("https://a.example.com", NOW - timedelta(days=15)),
        logo_item("https://a.example.com"),
        logo_item("https://a.example.com", fetched_at="not a date"),
    ],
)
def test_select_reusable_logos_skips_stale_or_unknown_age(item: dict):
    assert select_reusable_logos([item], ["https://a.example.com"], NOW) == {}


def test_select_reusable_logos_ignores_unknown_fields():
    item = logo_item("https://a.example.com", NOW, unknown="value")
    logos = select_reusable_logos([item], ["https://a.example.com"], NOW)

    assert "unknown" not in logos["https://a.example.com"][0]


def test_spider_start_reuses_logos(monkeypatch):
    urls = ["https://a.example.com", "https://b.example.com"]
    crawler = get_crawler(Spider)
    spider = Spider.from_crawler(crawler, links=[{"url": url} for url in urls])
    logo = JobLogo(**logo_item(urls[0], NOW))

    async def load_reusable_logos():
        return {urls[0]: [logo]}

    monkeypatch.setattr(spider, "_load_reusable_logos", load_reusable_logos)

    async def collect():
        return [request async for request in spider.start()]

    results = asyncio.run(collect())

    assert results[0] is logo
    assert isinstance(results[1], Request)
    assert results[1].url == urls[1]
    assert len(results) == 2
    assert crawler.stats.get_value("job_logos/reused") == 1


def test_spider_load_reusable_logos_not_on_apify():
    spider = Spider(links=[{"url": "https://a.example.com"}])

    assert asyncio.run(spider._load_reusable_logos()) == {}


def test_spider_load_reusable_logos_failure(
    monkeypatch, caplog, fake_actor: type[FakeActor]
):
    spider = Spider(links=[{"url": "https://a.example.com"}])

    class FailingClient:
        def actor(self, actor_id: str):
            raise ApifyClientError("Insufficient permissions")

    monkeypatch.setattr(fake_actor, "apify_client", FailingClient())
    monkeypatch.setattr(fake_actor, "is_at_home", staticmethod(lambda: True))

    with caplog.at_level("WARNING"):
        assert asyncio.run(spider._load_reusable_logos()) == {}

    assert caplog.messages == [
        "Failed to load logos from previous run: Insufficient permissions"
    ]


LAST_RUN = {
    "id": "run123",
    "actId": "abc",
    "userId": "user123",
    "startedAt": "2026-10-24T12:00:00.000Z",
    "status": "SUCCEEDED",
    "meta": {"origin": "SCHEDULER"},
    "stats": {},
    "options": {
        "build": "latest",
        "timeoutSecs": 600,
        "memoryMbytes": 1024,
        "diskMbytes": 2048,
    },
    "buildId": "build123",
    "defaultKeyValueStoreId": "kvs123",
    "defaultDatasetId": "dataset123",
    "defaultRequestQueueId": "queue123",
}


@pytest.fixture
def apify_api(fake_actor: type[FakeActor], monkeypatch: pytest.MonkeyPatch):
    """Real Apify client talking to a local stub of the Apify API"""
    state: dict[str, Any] = {"last_run": LAST_RUN, "items": [], "paths": []}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url = urlparse(self.path)
            state["paths"].append(url.path)
            if url.path == "/v2/actors/abc/runs/last":
                assert parse_qs(url.query)["status"] == ["SUCCEEDED"]
                if state["last_run"]:
                    self.send_json({"data": state["last_run"]})
                else:
                    error = {"type": "record-not-found", "message": "Not found"}
                    self.send_json({"error": error}, status=404)
            elif url.path == "/v2/datasets/dataset123/items":
                offset = int(parse_qs(url.query).get("offset", ["0"])[0])
                items = state["items"][offset:]
                self.send_json(
                    items,
                    headers={
                        "X-Apify-Pagination-Total": str(len(state["items"])),
                        "X-Apify-Pagination-Offset": str(offset),
                        "X-Apify-Pagination-Count": str(len(items)),
                        "X-Apify-Pagination-Limit": "1000",
                        "X-Apify-Pagination-Desc": "false",
                    },
                )
            else:
                self.send_json({"error": {"type": "page-not-found"}}, status=404)

        def send_json(self, data: Any, status: int = 200, headers=None):
            body = json.dumps(data).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        api_url = f"http://127.0.0.1:{server.server_address[1]}"
        client = ApifyClientAsync(token="token123", api_url=api_url, max_retries=1)
        monkeypatch.setattr(fake_actor, "apify_client", client)
        monkeypatch.setattr(fake_actor, "is_at_home", staticmethod(lambda: True))
        yield state
        server.shutdown()


def test_spider_load_reusable_logos(apify_api: dict[str, Any]):
    fetched_at = datetime.now(UTC) - timedelta(days=1)
    apify_api["items"] = [
        logo_item("https://a.example.com", fetched_at),
        logo_item("https://b.example.com", fetched_at),
    ]
    spider = Spider(links=[{"url": "https://a.example.com"}])

    logos = asyncio.run(spider._load_reusable_logos())

    assert list(logos) == ["https://a.example.com"]
    assert dict(logos["https://a.example.com"][0]) == apify_api["items"][0]
    assert apify_api["paths"][:2] == [
        "/v2/actors/abc/runs/last",
        "/v2/datasets/dataset123/items",
    ]


def test_spider_load_reusable_logos_no_previous_run(apify_api: dict[str, Any], caplog):
    apify_api["last_run"] = None
    spider = Spider(links=[{"url": "https://a.example.com"}])

    with caplog.at_level("INFO"):
        assert asyncio.run(spider._load_reusable_logos()) == {}

    assert "No previous successful run, nothing to reuse" in caplog.messages
    assert apify_api["paths"] == ["/v2/actors/abc/runs/last"]
