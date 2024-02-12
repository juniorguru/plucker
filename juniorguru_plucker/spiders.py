from typing import Any

from scrapy import Spider
from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from scrapy.statscollectors import StatsCollector


def run_spider(settings: Settings, spider_class: type[Spider]):
    crawler_process = CrawlerProcess(settings, install_root_handler=False)
    crawler_process.crawl(spider_class)
    stats_collector = get_stats_collector(crawler_process)
    crawler_process.start()
    raise_for_stats(stats_collector.get_stats())


def get_stats_collector(crawler_process: CrawlerProcess) -> StatsCollector:
    assert len(crawler_process.crawlers) == 1, "Exactly one crawler expected"
    crawler = crawler_process.crawlers.pop()
    return crawler.stats


def raise_for_stats(stats: dict[str, Any]):
    item_count = stats.get("item_scraped_count", 0)
    if item_count < 10:
        raise RuntimeError(f"Few items scraped: {item_count}")
    if reason := stats.get("finish_reason"):
        if reason != "finished":
            raise RuntimeError(f"Scraping finished with reason {reason!r}")
    if item_count := stats.get("item_dropped_reasons_count/MissingRequiredFields"):
        raise RuntimeError(f"Items missing required fields: {item_count}")
    if exc_count := stats.get("spider_exceptions"):
        raise RuntimeError(f"Exceptions raised: {exc_count}")
    if error_count := stats.get("log_count/ERROR"):
        raise RuntimeError(f"Errors logged: {error_count}")


class JobSpider(Spider):
    extra_item_pipelines = {
        "juniorguru_plucker.pipelines.required_fields_filter.Pipeline": 50,
        "juniorguru_plucker.pipelines.language_parser.Pipeline": 200,
        "juniorguru_plucker.pipelines.language_filter.Pipeline": 250,
    }

    @classmethod
    def update_settings(cls, settings: Settings):
        if cls.custom_settings and "ITEM_PIPELINES" in cls.custom_settings:
            raise NotImplementedError(
                "Setting custom_settings['ITEM_PIPELINES'] not supported"
            )
        super().update_settings(settings)
        settings["ITEM_PIPELINES"].update(cls.extra_item_pipelines)
