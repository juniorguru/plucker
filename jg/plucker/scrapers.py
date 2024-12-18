import logging
from pathlib import Path
from typing import Any, Generator, Type

import nest_asyncio
from apify import Actor, Configuration
from apify.scrapy.utils import apply_apify_settings
from scrapy import Item, Spider
from scrapy.crawler import CrawlerProcess
from scrapy.settings import BaseSettings, Settings
from scrapy.spiderloader import SpiderLoader as BaseSpiderLoader
from scrapy.statscollectors import StatsCollector


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
