import asyncio
import logging
import pickle
import threading
from pathlib import Path
from time import time
from typing import Any, Generator, Type

from apify import Actor, Configuration
from apify.apify_storage_client import ApifyStorageClient
from apify.scrapy.scheduler import (
    _TIMEOUT,
    _force_exit_event_loop,
    _run_async_coro,
    _shutdown_async_tasks,
    _start_event_loop,
)
from apify.scrapy.utils import apply_apify_settings
from apify.storages import KeyValueStore
from scrapy import Item, Request, Spider
from scrapy.crawler import CrawlerProcess, CrawlerRunner
from scrapy.http.headers import Headers
from scrapy.http.response import Response
from scrapy.responsetypes import responsetypes
from scrapy.settings import BaseSettings, Settings
from scrapy.spiderloader import SpiderLoader as BaseSpiderLoader
from scrapy.statscollectors import StatsCollector
from scrapy.utils.defer import deferred_to_future
from scrapy.utils.reactor import is_asyncio_reactor_installed
from scrapy.utils.request import RequestFingerprinterProtocol


logger = logging.getLogger("jg.plucker")


def run_spider(
    settings: Settings, spider_class: type[Spider], spider_params: dict[str, Any] | None
) -> None:
    # TODO use crawler runner instead? make run_spider() and run_actor() DRY?
    logger.debug(f"Spider params: {spider_params!r}")
    settings.set("SPIDER_PARAMS", spider_params)

    crawler_process = CrawlerProcess(settings, install_root_handler=False)
    crawler_process.crawl(spider_class)
    stats_collector = get_stats_collector(crawler_process)
    crawler_process.start()

    min_items = getattr(spider_class, "min_items", settings.getint("SPIDER_MIN_ITEMS"))
    logger.debug(f"Min items required: {min_items}")

    logger.debug(f"Custom evaluate_stats(): {hasattr(spider_class, 'evaluate_stats')}")
    evaluate_stats_fn = getattr(spider_class, "evaluate_stats", evaluate_stats)
    evaluate_stats_fn(stats_collector.get_stats(), min_items=min_items)


async def actor_main(spider_class: Type[Spider], spider_params: dict[str, Any] | None):
    async with Actor:
        Actor.log.info(f"Starting actor for spider {spider_class.name}")

        params = spider_params or (await Actor.get_input()) or {}
        proxy_config = params.pop("proxyConfig", None)

        settings = apply_apify_settings(proxy_config=proxy_config)
        settings.set("HTTPCACHE_STORAGE", "jg.plucker.scrapers.CacheStorage")
        settings.set("SPIDER_PARAMS", spider_params)

        Actor.log.info("Starting the spider")
        crawler_runner = CrawlerRunner(settings)
        await deferred_to_future(crawler_runner.crawl(spider_class))


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


def evaluate_stats(stats: dict[str, Any], min_items: int):
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
    # TODO implement gzipping

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
        self._eventloop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=lambda: _start_event_loop(self._eventloop), daemon=True
        )
        self._thread.start()

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
        self._kv = _run_async_coro(self._eventloop, open_kv())

    def close_spider(self, spider: Spider) -> None:
        logger.debug("Closing cache storage...")
        try:
            if self._eventloop.is_running():
                _run_async_coro(self._eventloop, _shutdown_async_tasks(self._eventloop))
            self._eventloop.call_soon_threadsafe(self._eventloop.stop)
            self._thread.join(timeout=_TIMEOUT)
            if self._thread.is_alive():
                logger.warning(
                    "Background thread for cache storage didn't exit cleanly! Forcing shutdown..."
                )
                _force_exit_event_loop(self._eventloop, self._thread)
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

        seconds = _run_async_coro(self._eventloop, self._kv.get_value(f"{key}_time"))
        if seconds is None:
            logger.debug("Cache miss", extra={"request": request})
            return None

        if 0 < self.expiration_secs < time() - seconds:
            logger.debug("Cache expired", extra={"request": request})
            return None

        value = _run_async_coro(self._eventloop, self._kv.get_value(f"{key}_data"))
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
        _run_async_coro(self._eventloop, self._kv.set_value(f"{key}_data", value))
        _run_async_coro(self._eventloop, self._kv.set_value(f"{key}_time", time()))
