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
