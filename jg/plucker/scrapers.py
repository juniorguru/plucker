import asyncio
import logging
import pickle
from threading import Thread
from pathlib import Path
import threading
from typing import Any, Coroutine, Generator, Type, cast

import nest_asyncio
from apify import Actor, Configuration
from apify.apify_storage_client import ApifyStorageClient
from apify.scrapy.requests import to_apify_request, to_scrapy_request
from apify.scrapy.utils import apply_apify_settings
from apify.storages import Dataset, KeyValueStore, RequestQueue
from crawlee import Request as ApifyRequest
from crawlee._utils.crypto import crypto_random_object_id
from crawlee.storage_clients import MemoryStorageClient  # pyright: ignore
from crawlee.storage_clients.models import ProcessedRequest
from itemadapter import ItemAdapter  # pyright: ignore
from scrapy import Item, Request, Spider
from scrapy.core.scheduler import BaseScheduler
from scrapy.crawler import CrawlerProcess
from scrapy.http.headers import Headers
from scrapy.http.response import Response
from scrapy.responsetypes import responsetypes
from scrapy.settings import BaseSettings, Settings
from scrapy.spiderloader import SpiderLoader as BaseSpiderLoader
from scrapy.statscollectors import StatsCollector
from scrapy.utils.reactor import is_asyncio_reactor_installed
from scrapy.utils.request import RequestFingerprinterProtocol


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

    logger.debug(f"Custom evaluate_stats(): {hasattr(spider_class, 'evaluate_stats')}")
    evaluate_stats_fn = getattr(spider_class, "evaluate_stats", evaluate_stats)
    evaluate_stats_fn(stats_collector.get_stats(), min_items=min_items)


def run_actor(
    settings: Settings, spider_class: Type[Spider], spider_params: dict[str, Any] | None
) -> None:
    run_async(Actor.init())
    Actor._apify_client.http_client.httpx_client.headers["Connection"] = "close"
    try:
        Actor.log.info(f"Spider {spider_class.name}")
        Actor.log.info("Reading input")
        spider_params = dict(spider_params or (run_async(Actor.get_input())) or {})
        proxy_config = spider_params.pop("proxyConfig", None)

        Actor.log.info("Applying Apify settings")
        settings = apply_apify_settings(settings=settings, proxy_config=proxy_config)

        Actor.log.info("Overriding Apify settings with custom ones")
        settings["HTTPCACHE_STORAGE"] = "jg.plucker.scrapers.CacheStorage"
        del settings["ITEM_PIPELINES"][
            "apify.scrapy.pipelines.ActorDatasetPushPipeline"
        ]
        settings["ITEM_PIPELINES"]["jg.plucker.scrapers.Pipeline"] = 1000
        settings["SCHEDULER"] = "jg.plucker.scrapers.Scheduler"

        Actor.log.info("Purging the default dataset")
        dataset = cast(Dataset, run_async(Actor.open_dataset()))
        run_async(dataset.drop())

        Actor.log.info("Purging the default request queue")
        request_queue = cast(RequestQueue, run_async(Actor.open_request_queue()))
        run_async(request_queue.drop())

        Actor.log.info("Starting the spider")
        run_spider(settings, spider_class, spider_params)
    except Exception as e:
        run_async(Actor.fail(exception=e))
    else:
        run_async(Actor.exit())


def configure_async():
    # nest_asyncio.apply()
    pass


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


def run_async(coroutine: Coroutine) -> Any:
    result = None

    def run() -> None:
        nonlocal result
        asyncio.set_event_loop(asyncio.new_event_loop())
        print(
            f"Thread {threading.current_thread().name} has event loop: {asyncio.get_event_loop()}, executing {coroutine.__name__}"
        )
        result = asyncio.run(coroutine)

    t = Thread(target=run)
    t.start()
    t.join()
    return result


class CacheStorage:
    # TODO implement expiration as in https://github.com/scrapy/scrapy/blob/a8d9746f562681ed5a268148ec959dcf0881d859/scrapy/extensions/httpcache.py#L250
    # TODO implement gzipping

    def __init__(self, settings: BaseSettings):
        if not is_asyncio_reactor_installed():
            raise ValueError(
                f"{self.__class__.__qualname__} requires the asyncio Twisted reactor. "
                "Make sure you have it configured in the TWISTED_REACTOR setting. See the asyncio "
                "documentation of Scrapy for more information.",
            )
        self.spider: Spider | None = None
        self._kv: KeyValueStore | None = None
        self._fingerprinter: RequestFingerprinterProtocol | None = None

    def open_spider(self, spider: Spider) -> None:
        logger.debug("Using Apify key value cache storage", extra={"spider": spider})
        self.spider = spider
        self._fingerprinter = spider.crawler.request_fingerprinter
        self._kv = run_async(
            Actor.open_key_value_store(name=f"httpcache-{spider.name}")
        )

    def close_spider(self, spider: Spider) -> None:
        pass

    def retrieve_response(self, spider: Spider, request: Request) -> Response | None:
        assert self._kv is not None, "Key value store not initialized"
        assert self._fingerprinter is not None, "Request fingerprinter not initialized"

        key = self._fingerprinter.fingerprint(request).hex()
        value = run_async(self._kv.get_value(key))
        if value is None:
            return None  # not cached

        data = pickle.loads(value)
        url = data["url"]
        status = data["status"]
        headers = Headers(data["headers"])
        body = data["body"]
        respcls = responsetypes.from_args(headers=headers, url=url, body=body)
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
        run_async(self._kv.set_value(key, value))


class Pipeline:
    async def process_item(
        self,
        item: Item,
        spider: Spider,
    ) -> Item:
        item_dict = ItemAdapter(item).asdict()
        Actor.log.debug(
            f"Pushing item={item_dict} produced by spider={spider} to the dataset."
        )
        run_async(Actor.push_data(item_dict))
        return item


class Scheduler(BaseScheduler):
    def __init__(self) -> None:
        self._rq: RequestQueue | None = None
        self.spider: Spider | None = None

    def open(self, spider: Spider) -> None:  # this has to be named "open"
        self.spider = spider
        self._rq = run_async(Actor.open_request_queue())

    def has_pending_requests(self) -> bool:
        assert self._rq is not None, "Request queue not initialized"

        is_finished = cast(bool, run_async(self._rq.is_finished()))
        return not is_finished

    def enqueue_request(self, request: Request) -> bool:
        assert self.spider is not None, "Spider not initialized"
        assert self._rq is not None, "Request queue not initialized"

        call_id = crypto_random_object_id(8)
        Actor.log.debug(
            f"[{call_id}]: ApifyScheduler.enqueue_request was called (scrapy_request={request})..."
        )
        apify_request = to_apify_request(request, spider=self.spider)
        if apify_request is None:
            Actor.log.error(
                f"Request {request} was not enqueued because it could not be converted to Apify request."
            )
            return False
        Actor.log.debug(
            f"[{call_id}]: scrapy_request was transformed to apify_request (apify_request={apify_request})"
        )
        result = cast(ProcessedRequest, run_async(self._rq.add_request(apify_request)))
        Actor.log.debug(f"[{call_id}]: rq.add_request.result={result}...")
        return bool(result.was_already_present)

    def next_request(self) -> Request | None:
        assert self._rq is not None, "Request queue not initialized"
        assert self.spider is not None, "Spider not initialized"

        call_id = crypto_random_object_id(8)
        Actor.log.debug(f"[{call_id}]: ApifyScheduler.next_request was called...")
        apify_request = cast(ApifyRequest, run_async(self._rq.fetch_next_request()))
        Actor.log.debug(
            f"[{call_id}]: a new apify_request from the scheduler was fetched (apify_request={apify_request})"
        )
        if apify_request is None:
            return None

        # Let the Request Queue know that the request is being handled. Every request should be marked as handled,
        # retrying is handled by the Scrapy's RetryMiddleware.
        run_async(self._rq.mark_request_as_handled(apify_request))

        scrapy_request = to_scrapy_request(apify_request, spider=self.spider)
        Actor.log.debug(
            f"[{call_id}]: apify_request was transformed to the scrapy_request which is gonna be returned "
            f"(scrapy_request={scrapy_request})",
        )
        return scrapy_request
