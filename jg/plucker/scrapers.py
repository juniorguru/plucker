import logging
from pathlib import Path
from typing import Annotated, Any, Coroutine, Generator, Literal, Type

from apify import Actor
from apify.scrapy import run_scrapy_actor
from apify.scrapy.utils import apply_apify_settings
from pydantic import BaseModel, HttpUrl, PlainSerializer
from scrapy import Item, Spider
from scrapy.crawler import Crawler, CrawlerRunner
from scrapy.settings import BaseSettings
from scrapy.spiderloader import SpiderLoader as BaseSpiderLoader
from scrapy.statscollectors import StatsT
from scrapy.utils.defer import deferred_to_future
from scrapy.utils.project import get_project_settings
from scrapy.utils.reactor import install_reactor


logger = logging.getLogger("jg.plucker")


# Trying to be at least somewhat compatible with 'requestListSources'
# See https://docs.apify.com/platform/actors/development/actor-definition/input-schema/specification/v1
class Link(BaseModel):
    url: Annotated[HttpUrl, PlainSerializer(str)]
    method: Literal["GET"] = "GET"


def start_reactor(coroutine: Coroutine) -> None:
    settings = get_project_settings()
    install_reactor(settings["TWISTED_REACTOR"])
    run_scrapy_actor(coroutine)


async def run_as_spider(
    spider_class: Type[Spider], spider_params: dict[str, Any] | None
) -> None:
    params = spider_params or {}
    settings = get_project_settings()

    logger.info("Starting the spider")
    runner = CrawlerRunner(settings)
    crawler = runner.create_crawler(spider_class)

    logger.debug(f"Spider params: {params!r}")
    await deferred_to_future(runner.crawl(crawler, **params))

    check_crawl_results(crawler)


async def run_as_actor(
    spider_class: Type[Spider], spider_params: dict[str, Any] | None
):
    async with Actor:
        logger.info(f"Starting actor for spider {spider_class.name}")

        params = spider_params or (await Actor.get_input()) or {}
        proxy_config = params.pop("proxyConfig", None)
        logger.debug(f"Proxy config: {proxy_config!r}")

        settings = apply_apify_settings(proxy_config=proxy_config)
        settings["HTTPCACHE_STORAGE"] = "jg.plucker.cache.CacheStorage"
        settings["ITEM_PIPELINES"]["jg.plucker.pipelines.ImagePipeline"] = 500

        logger.info("Starting the spider")
        runner = CrawlerRunner(settings)
        crawler = runner.create_crawler(spider_class)

        logger.debug(f"Spider params: {params!r}")
        await deferred_to_future(runner.crawl(crawler, **params))

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


def parse_links(links: list[Link] | None) -> list[str]:
    return list(set(str(link.url) for link in map(Link.model_validate, links or [])))
