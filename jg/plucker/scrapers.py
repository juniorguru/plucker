import logging
import random
from pathlib import Path
from typing import Any, Generator, Type
from urllib.parse import urlparse

import nest_asyncio
from apify import Actor, Configuration
from apify.scrapy.utils import apply_apify_settings
from scrapy import Item, Request, Spider
from scrapy.crawler import CrawlerProcess
from scrapy.http import TextResponse
from scrapy.settings import BaseSettings, Settings
from scrapy.spiderloader import SpiderLoader as BaseSpiderLoader
from scrapy.statscollectors import StatsCollector
from scrapy.utils.response import response_status_message
from scrapy_fake_useragent.middleware import RetryUserAgentMiddleware


logger = logging.getLogger("jg.plucker")


def run_spider(
    settings: Settings, spider_class: type[Spider], spider_params: dict[str, Any] | None
) -> None:
    logger.debug(f"Spider params: {spider_params!r}")
    settings.set("SPIDER_PARAMS", spider_params)

    crawler_process = CrawlerProcess(settings, install_root_handler=False)
    crawler_process.crawl(spider_class)
    stats_collector = get_stats_collector(crawler_process)
    crawler_process.start()

    min_items = getattr(spider_class, "min_items", settings.getint("SPIDER_MIN_ITEMS"))
    logger.debug(f"Min items required: {min_items}")
    raise_for_stats(stats_collector.get_stats(), min_items=min_items)


async def run_actor(
    settings: Settings, spider_class: Type[Spider], spider_params: dict[str, Any] | None
) -> None:
    config = Configuration.get_global_configuration()
    config.purge_on_start = True
    async with Actor:
        Actor.log.info(f"Spider {spider_class.name}")
        spider_params = dict(spider_params or (await Actor.get_input()) or {})
        proxy_config = spider_params.pop("proxyConfig", None)
        settings = apply_apify_settings(settings=settings, proxy_config=proxy_config)
        run_spider(settings, spider_class, spider_params)


def configure_async():
    nest_asyncio.apply()


def iter_actor_paths(path: Path | str) -> Generator[Path, None, None]:
    for actor_spec in Path(path).rglob(".actor/actor.json"):
        yield actor_spec.parent.parent.relative_to(".")


def get_spider_module_name(actor_path: Path | str) -> str:
    return f"{str(actor_path).replace('/', '.')}.spider"


class SpiderLoader(BaseSpiderLoader):
    def __init__(self, settings: BaseSettings):
        super().__init__(settings)
        if not self.spider_modules:
            spider_path = settings.get("SPIDER_LOADER_SPIDERS_PATH", ".")
            self.spider_modules = list(
                map(get_spider_module_name, iter_actor_paths(spider_path))
            )
        self._load_all_spiders()


def generate_schema(item_class: Type[Item]) -> dict:
    properties = {
        name: (
            {
                "label": name,
                "format": kwargs.get("apify_format"),
            }
            if kwargs.get("apify_format")
            else {
                "label": name,
            }
        )
        for name, kwargs in sorted(item_class.fields.items())
    }
    return {
        "title": item_class.__name__,
        "actorSpecification": 1,
        "views": {
            "titles": {
                "title": item_class.__name__,
                "transformation": {"fields": sorted(properties.keys())},
                "display": {
                    "component": "table",
                    "properties": properties,
                },
            }
        },
    }


def get_stats_collector(crawler_process: CrawlerProcess) -> StatsCollector:
    assert len(crawler_process.crawlers) == 1, "Exactly one crawler expected"
    crawler = crawler_process.crawlers.pop()
    return crawler.stats


class StatsError(RuntimeError):
    pass


def raise_for_stats(stats: dict[str, Any], min_items: int):
    item_count = stats.get("item_scraped_count", 0)
    if exc_count := stats.get("spider_exceptions"):
        raise StatsError(f"Exceptions raised: {exc_count}")
    if critical_count := stats.get("log_count/CRITICAL"):
        raise StatsError(f"Critical errors logged: {critical_count}")
    if error_count := stats.get("log_count/ERROR"):
        raise StatsError(f"Errors logged: {error_count}")
    if item_count < min_items:
        raise StatsError(f"Few items scraped: {item_count}")
    if reason := stats.get("finish_reason"):
        if reason != "finished":
            raise StatsError(f"Scraping finished with reason {reason!r}")
    if item_count := stats.get("item_dropped_reasons_count/MissingRequiredFields"):
        raise StatsError(f"Items missing required fields: {item_count}")


class RetryMiddleware(RetryUserAgentMiddleware):
    def process_response(
        self, request: Request, response: TextResponse, spider: Spider
    ) -> TextResponse | Request:
        if request.meta.get("dont_retry", False):
            return response

        if response.status in self.retry_http_codes:
            reason = response_status_message(response.status)
            request.headers.update(self.get_random_headers())
            return self._retry(request, reason, spider) or response

        if is_linkedin_block(response.url):
            if original_url := request.meta.get("original_url"):
                reason = f"Got {response.url}"
                retry_request = request.replace(
                    url=original_url,
                    headers=request.headers | self.get_random_headers(),
                )
                return self._retry(retry_request, reason, spider) or response
            raise ValueError("Cannot retry without 'original_url' in request meta")

        return response

    def get_random_headers(self) -> dict:
        return {
            "Accept": random.choice(
                [
                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/png,image/svg+xml,*/*;q=0.8",
                    "*/*",
                ]
            ),
            "Accept-Language": random.choice(
                [
                    "cs;q=0.8,en;q=0.6",
                    "en-us",
                    "en-US,en;q=0.8,cs;q=0.6,sk;q=0.4,es;q=0.2",
                ]
            ),
            "User-Agent": self._ua_provider.get_random_ua(),
            "Referer": random.choice(
                [
                    "https://www.linkedin.com/",
                    "https://duckduckgo.com/",
                    "https://www.google.com/",
                    "https://www.bing.com/",
                ]
            ),
        }


def is_linkedin_block(url: str) -> bool:
    url_parts = urlparse(url)
    domain = ".".join(url_parts.netloc.split(".")[-2:])
    if domain != "linkedin.com":
        return False
    if not url_parts.path.strip("/"):
        return True
    return False
