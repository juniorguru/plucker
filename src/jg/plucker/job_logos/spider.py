from collections.abc import AsyncGenerator, Generator, Iterable
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from io import BytesIO
from typing import Any
from urllib.parse import urljoin

from apify import Actor
from apify_client.errors import ApifyClientError
from favicon import Icon, favicon
from PIL import Image
from scrapy import Request, Spider as BaseSpider
from scrapy.exceptions import DownloadTimeoutError
from scrapy.http.response import Response
from twisted.internet.error import TCPTimedOutError, TimeoutError
from twisted.python.failure import Failure

from jg.plucker.items import JobLogo
from jg.plucker.scrapers import evaluate_stats, parse_links


class Format(StrEnum):
    PNG = "png"
    JPG = "jpg"
    ICO = "ico"
    WEBP = "webp"
    BMP = "bmp"
    GIF = "gif"
    AVIF = "avif"

    @classmethod
    def from_content_type(cls, content_type: str) -> Format:
        if content_type.startswith("image/png"):
            return cls.PNG
        elif content_type.startswith("image/jpeg"):
            return cls.JPG
        elif content_type.startswith("image/x-icon"):
            return cls.ICO
        elif content_type.startswith("image/webp"):
            return cls.WEBP
        elif content_type.startswith("image/bmp"):
            return cls.BMP
        elif content_type.startswith("image/gif"):
            return cls.GIF
        elif content_type.startswith("image/avif"):
            return cls.AVIF
        raise ValueError(f"Unsupported content type: {content_type!r}")


TIMEOUT_EXCEPTIONS = (DownloadTimeoutError, TimeoutError, TCPTimedOutError)

# Keeps logos fresh and every reused image URL inside the data retention period
REUSE_MAX_AGE = timedelta(days=14)


class Spider(BaseSpider):
    name = "job-logos"

    custom_settings = {
        # Logos and favicons are small, no need to wait for long
        "DOWNLOAD_TIMEOUT": 30,
    }

    min_items = 1

    @classmethod
    def evaluate_stats(cls, stats: dict[str, Any], min_items: int) -> None:
        # Giving up on retrying a timed out request logs an error, but such
        # requests get skipped, so it's not an error of the scraper
        timeouts_count = stats.get("job_logos/timeouts_skipped", 0)
        error_count = stats.get("log_count/ERROR", 0)
        stats_copy = stats.copy()
        stats_copy["log_count/ERROR"] = max(0, error_count - timeouts_count)
        return evaluate_stats(stats_copy, min_items)

    def __init__(
        self, name: str | None = None, links: list[dict[str, str]] | None = None
    ):
        super().__init__(name)
        parse_links(links)  # validates, but normalizes URLs, which wouldn't match
        self._start_urls = list(dict.fromkeys(link["url"] for link in links or []))

    async def start(self) -> AsyncGenerator[Request | JobLogo]:
        reusable_logos = await self._load_reusable_logos()
        for url in self._start_urls:
            if logos := reusable_logos.get(url):
                self.logger.info(f"Reusing {len(logos)} logos of {url}")
                self.crawler.stats.inc_value("job_logos/reused", len(logos))
                for logo in logos:
                    yield logo
                continue
            # The input URL as given, so that it matches on the junior.guru side
            yield Request(
                url,
                callback=self.parse,
                errback=self.on_error,
                cb_kwargs={"source_url": url},
                dont_filter=True,
            )

    async def _load_reusable_logos(self) -> dict[str, list[JobLogo]]:
        if not Actor.is_at_home():
            self.logger.info("Not on Apify, nothing to reuse")
            return {}
        try:
            run_client = Actor.apify_client.actor(Actor.configuration.actor_id)
            run = await run_client.last_run(status="SUCCEEDED").get()
            if not run:
                self.logger.info("No previous successful run, nothing to reuse")
                return {}
            self.logger.info(f"Loading logos from previous run {run.id}")
            dataset_client = Actor.apify_client.dataset(run.default_dataset_id)
            items = [item async for item in dataset_client.iterate_items()]
        except ApifyClientError as e:
            self.logger.warning(f"Failed to load logos from previous run: {e}")
            return {}
        return select_reusable_logos(items, self._start_urls, datetime.now(UTC))

    def on_error(self, failure: Failure) -> Failure | None:
        # The site not responding isn't our problem, junior.guru falls back
        # to a generated logo
        if failure.check(*TIMEOUT_EXCEPTIONS):
            self.logger.warning(f"Skipping {failure.request.url}: timed out")
            self.crawler.stats.inc_value("job_logos/timeouts_skipped")
            return None
        return failure

    def parse(
        self, response: Response, source_url: str
    ) -> Generator[Request | JobLogo]:
        if not response.request:
            raise ValueError("Response does not have a request")
        request = response.request

        details = []
        if response.url != request.url:
            details.append(f"redirected from {request.url}")
        if source_url != request.url:
            details.append(f"originally {source_url}")
        details = f" ({' '.join(details)})" if details else ""
        self.logger.info(f"Processing {response.url}{details}")

        content_type = (response.headers.get("Content-Type") or b"").decode("utf8")
        if not content_type.startswith(("image/", "text/")):
            self.logger.warning(f"Declared content type: {content_type!r}")
        elif "image/svg" in content_type:
            self.logger.warning("SVG images are not supported")
            return
        else:
            self.logger.debug(f"Declared content type: {content_type!r}")

        try:
            html = response.text
        except AttributeError:
            self.logger.debug("Assuming image URL")
            with Image.open(BytesIO(response.body)) as img:
                content_type = img.get_format_mimetype() or content_type
                self.logger.debug(f"Detected content type: {content_type!r}")
                width, height = img.size
                self.logger.debug(f"Image size: {width}x{height}")
            yield JobLogo(
                image_url=response.body,
                original_image_url=response.url,
                width=width,
                height=height,
                format=Format.from_content_type(content_type),
                source_url=source_url,
                fetched_at=datetime.now(UTC).isoformat(),
            )
        else:
            self.logger.debug("Assuming company homepage URL")
            favicon_url = urljoin(response.url, "/favicon.ico")
            self.logger.debug(f"Favicon URL: {favicon_url}")
            if response.url == favicon_url:
                self.logger.warning("Favicon URL doesn't return an image")
                return
            yield Request(
                favicon_url,
                callback=self.parse,
                errback=self.on_error,
                cb_kwargs={"source_url": source_url},
            )
            icons: set[Icon] = {
                icon
                for icon in favicon.tags(response.url, html)
                if icon.url != favicon_url
            }
            self.logger.debug(f"Found {len(icons)} other URLs in HTML tags")
            for icon in icons:
                if icon.url.startswith("data:"):
                    self.logger.warning(f"Skipping data URL favicon at {response.url}")
                    continue
                yield Request(
                    icon.url,
                    callback=self.parse,
                    errback=self.on_error,
                    cb_kwargs={"source_url": source_url},
                )


def select_reusable_logos(
    items: Iterable[dict[str, Any]], urls: Iterable[str], now: datetime
) -> dict[str, list[JobLogo]]:
    urls = set(urls)
    logos: dict[str, list[JobLogo]] = {}
    for item in items:
        if item.get("source_url") not in urls:
            continue
        try:
            fetched_at = datetime.fromisoformat(item["fetched_at"])
        except KeyError, TypeError, ValueError:
            continue  # from before fetched_at existed
        if now - fetched_at > REUSE_MAX_AGE:
            continue
        logo = JobLogo(**{key: item[key] for key in JobLogo.fields if key in item})
        logos.setdefault(item["source_url"], []).append(logo)
    return logos
