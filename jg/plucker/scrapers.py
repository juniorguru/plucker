import asyncio
import logging
import os
import pickle
from pathlib import Path
from time import time
from typing import Any, Coroutine, Generator, Type

from apify import Actor, Configuration
from apify.apify_storage_client import ApifyStorageClient
from apify.scrapy import run_scrapy_actor
from apify.scrapy._async_thread import AsyncThread
from apify.scrapy.utils import apply_apify_settings
from apify.storages import KeyValueStore
from scrapy import Item, Request, Spider
from scrapy.crawler import Crawler, CrawlerRunner
from scrapy.http.headers import Headers
from scrapy.http.response import Response
from scrapy.responsetypes import responsetypes
from scrapy.settings import BaseSettings
from scrapy.spiderloader import SpiderLoader as BaseSpiderLoader
from scrapy.statscollectors import StatsT
from scrapy.utils.defer import deferred_to_future
from scrapy.utils.project import get_project_settings
from scrapy.utils.reactor import is_asyncio_reactor_installed
from scrapy.utils.request import RequestFingerprinterProtocol
from twisted.internet import asyncioreactor


logger = logging.getLogger("jg.plucker")


def start_reactor(coroutine: Coroutine) -> None:
    asyncioreactor.install(asyncio.get_event_loop())
    run_scrapy_actor(coroutine)


async def run_as_spider(
    spider_class: Type[Spider], spider_params: dict[str, Any] | None
) -> None:
    settings = get_project_settings()
    settings.set("SPIDER_PARAMS", spider_params)
    logger.debug(f"Spider params: {spider_params!r}")

    logger.info("Starting the spider")
    runner = CrawlerRunner(settings)
    crawler = runner.create_crawler(spider_class)

    await deferred_to_future(runner.crawl(crawler))

    check_crawl_results(crawler)


async def run_as_actor(
    spider_class: Type[Spider], spider_params: dict[str, Any] | None
):
    # workaround https://github.com/apify/apify-sdk-python/issues/401
    os.environ["SCRAPY_SETTINGS_MODULE"] = "jg.plucker.settings"

    async with Actor:
        logger.info(f"Starting actor for spider {spider_class.name}")

        params = spider_params or (await Actor.get_input()) or {}
        proxy_config = params.pop("proxyConfig", None)
        logger.debug(f"Proxy config: {proxy_config!r}")

        settings = apply_apify_settings(proxy_config=proxy_config)
        settings.set("HTTPCACHE_STORAGE", "jg.plucker.scrapers.CacheStorage")
        settings.set("SPIDER_PARAMS", spider_params)
        logger.debug(f"Spider params: {spider_params!r}")

        logger.info("Starting the spider")
        runner = CrawlerRunner(settings)
        crawler = runner.create_crawler(spider_class)

        await deferred_to_future(runner.crawl(crawler))

        check_crawl_results(crawler)


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


def check_crawl_results(crawler: Crawler) -> None:
    spider_class = crawler.spidercls

    assert crawler.stats is not None, "Stats collector not initialized"
    stats = crawler.stats.get_stats()
    assert stats, "Stats not collected"

    default_min_items = crawler.settings.getint("SPIDER_MIN_ITEMS")
    min_items = getattr(spider_class, "min_items", default_min_items)
    logger.debug(f"Min items required: {min_items}")

    logger.debug(f"Custom evaluate_stats(): {hasattr(spider_class, 'evaluate_stats')}")
    evaluate_stats_fn = getattr(spider_class, "evaluate_stats", evaluate_stats)
    evaluate_stats_fn(stats, min_items)


class StatsError(RuntimeError):
    pass


def evaluate_stats(stats: StatsT, min_items: int):
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


class CacheStorage:
    def __init__(self, settings: BaseSettings):
        if not is_asyncio_reactor_installed():
            raise ValueError(
                f"{self.__class__.__qualname__} requires the asyncio Twisted reactor. "
                "Make sure you have it configured in the TWISTED_REACTOR setting. See the asyncio "
                "documentation of Scrapy for more information.",
            )
        self.expiration_secs: int = settings.getint("HTTPCACHE_EXPIRATION_SECS")
        self.spider: Spider | None = None
        self._kv: KeyValueStore | None = None
        self._fingerprinter: RequestFingerprinterProtocol | None = None

        logger.debug("Starting background thread for cache storage's event loop")
        self._async_thread = AsyncThread()

    def open_spider(self, spider: Spider) -> None:
        logger.debug("Using Apify key value cache storage", extra={"spider": spider})
        self.spider = spider
        self._fingerprinter = spider.crawler.request_fingerprinter
        kv_name = f"httpcache-{spider.name}"

        async def open_kv() -> KeyValueStore:
            config = Configuration.get_global_configuration()
            if config.is_at_home:
                storage_client = ApifyStorageClient.from_config(config)
                return await KeyValueStore.open(
                    name=kv_name, storage_client=storage_client
                )
            return await KeyValueStore.open(name=kv_name)

        logger.debug(f"Opening cache storage's {kv_name!r} key value store")
        self._kv = self._async_thread.run_coro(open_kv())

    def close_spider(self, spider: Spider) -> None:
        logger.debug("Closing cache storage...")
        try:
            self._async_thread.close()
        except KeyboardInterrupt:
            logger.warning("Shutdown interrupted by KeyboardInterrupt!")
        except Exception:
            logger.exception("Exception occurred while shutting down cache storage")
        finally:
            logger.debug("Cache storage closed")

    def retrieve_response(self, spider: Spider, request: Request) -> Response | None:
        assert self._kv is not None, "Key value store not initialized"
        assert self._fingerprinter is not None, "Request fingerprinter not initialized"

        key = self._fingerprinter.fingerprint(request).hex()

        seconds = self._async_thread.run_coro(self._kv.get_value(f"{key}_time"))
        if seconds is None:
            logger.debug("Cache miss", extra={"request": request})
            return None

        if 0 < self.expiration_secs < time() - seconds:
            logger.debug("Cache expired", extra={"request": request})
            self._async_thread.run_coro(self._kv.set_value(f"{key}_data", None))
            self._async_thread.run_coro(self._kv.set_value(f"{key}_time", None))
            return None

        value = self._async_thread.run_coro(self._kv.get_value(f"{key}_data"))
        if value is None:
            logger.debug("Cache miss", extra={"request": request})
            return None

        data = pickle.loads(value)
        url = data["url"]
        status = data["status"]
        headers = Headers(data["headers"])
        body = data["body"]
        respcls = responsetypes.from_args(headers=headers, url=url, body=body)

        logger.debug("Cache hit", extra={"request": request})
        return respcls(url=url, headers=headers, status=status, body=body)

    def store_response(
        self, spider: Spider, request: Request, response: Response
    ) -> None:
        assert self._kv is not None, "Key value store not initialized"
        assert self._fingerprinter is not None, "Request fingerprinter not initialized"

        key = self._fingerprinter.fingerprint(request).hex()
        data = {
            "status": response.status,
            "url": response.url,
            "headers": dict(response.headers),
            "body": response.body,
        }
        value = pickle.dumps(data, protocol=4)
        self._async_thread.run_coro(self._kv.set_value(f"{key}_data", value))
        self._async_thread.run_coro(self._kv.set_value(f"{key}_time", time()))
