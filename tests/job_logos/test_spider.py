import asyncio
from io import BytesIO

from PIL import Image
from scrapy import Request
from scrapy.http import HtmlResponse, Response

from jg.plucker.items import JobLogo
from jg.plucker.job_logos.spider import Spider


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
