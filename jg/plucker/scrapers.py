import hashlib
from pathlib import Path
from typing import Any, Generator, Self, Type

import nest_asyncio
from apify import Actor, Configuration
from apify.scrapy.middlewares.apify_proxy import ApifyHttpProxyMiddleware
from apify.scrapy.utils import apply_apify_settings
from playwright.sync_api import Error as PlaywrightError
from scrapy import Item, Request, Spider
from scrapy.crawler import Crawler, CrawlerProcess
from scrapy.settings import BaseSettings, Settings
from scrapy.spiderloader import SpiderLoader as BaseSpiderLoader
from scrapy.statscollectors import StatsCollector


def run_spider(settings: Settings, spider_class: type[Spider]):
    crawler_process = CrawlerProcess(settings, install_root_handler=False)
    crawler_process.crawl(spider_class)
    stats_collector = get_stats_collector(crawler_process)
    crawler_process.start()
    raise_for_stats(stats_collector.get_stats())


async def run_actor(settings: Settings, spider_class: Type[Spider]) -> None:
    config = Configuration.get_global_configuration()
    config.purge_on_start = True
    async with Actor:
        Actor.log.info(f"Spider {spider_class.name}")
        actor_input = await Actor.get_input() or {}
        proxy_config = actor_input.get("proxyConfig")
        settings = apply_apify_settings(settings=settings, proxy_config=proxy_config)

        # use custom proxy middleware
        priority = settings["DOWNLOADER_MIDDLEWARES"].pop(
            "apify.scrapy.middlewares.ApifyHttpProxyMiddleware"
        )
        settings["DOWNLOADER_MIDDLEWARES"][
            "jg.plucker.scrapers.PlaywrightApifyHttpProxyMiddleware"
        ] = priority

        run_spider(settings, spider_class)


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


def raise_for_stats(stats: dict[str, Any]):
    item_count = stats.get("item_scraped_count", 0)
    if exc_count := stats.get("spider_exceptions"):
        raise StatsError(f"Exceptions raised: {exc_count}")
    if critical_count := stats.get("log_count/CRITICAL"):
        raise StatsError(f"Critical errors logged: {critical_count}")
    if error_count := stats.get("log_count/ERROR"):
        raise StatsError(f"Errors logged: {error_count}")
    if item_count < 10:
        raise StatsError(f"Few items scraped: {item_count}")
    if reason := stats.get("finish_reason"):
        if reason != "finished":
            raise StatsError(f"Scraping finished with reason {reason!r}")
    if item_count := stats.get("item_dropped_reasons_count/MissingRequiredFields"):
        raise StatsError(f"Items missing required fields: {item_count}")


class PlaywrightApifyHttpProxyMiddleware(ApifyHttpProxyMiddleware):
    @classmethod
    def from_crawler(cls, crawler: Crawler) -> Self:
        Actor.log.info("Using customized ApifyHttpProxyMiddleware.")
        return cls(super().from_crawler(crawler)._proxy_settings)

    async def process_request(self, request: Request, spider: Spider):
        if request.meta.get("playwright"):
            Actor.log.debug(
                f"ApifyHttpProxyMiddleware.process_request: playwright=True, request={request}, spider={spider}"
            )
            url = await self._get_new_proxy_url()

            if not (url.username and url.password):
                raise ValueError(
                    "Username and password must be provided in the proxy URL."
                )

            proxy = url.geturl()
            proxy_hash = hashlib.sha1(proxy.encode()).hexdigest()[0:8]
            context_name = f"proxy_{proxy_hash}"
            Actor.log.info(f"Using Playwright context {context_name}")
            request.meta.update(
                {
                    "playwright_context": f"proxy_{context_name}",
                    "playwright_context_kwargs": {
                        "proxy": {
                            "server": proxy,
                            "username": url.username,
                            "password": url.password,
                        },
                    },
                }
            )
            Actor.log.debug(
                f"ApifyHttpProxyMiddleware.process_request: updated request.meta={request.meta}"
            )
        else:
            await super().process_request(request, spider)

    def process_exception(
        self: ApifyHttpProxyMiddleware,
        request: Request,
        exception: Exception,
        spider: Spider,
    ) -> None | Request:
        if request := super().process_exception(request, exception, spider):
            return request
        if isinstance(exception, PlaywrightError):
            Actor.log.warning(
                f'ApifyHttpProxyMiddleware: Playwright error occurred for request="{request}", reason="{exception}", skipping...'
            )
            return request
