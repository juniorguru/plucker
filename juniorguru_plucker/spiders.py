from scrapy import Spider
from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from scrapy.statscollectors import StatsCollector


def run_spider(settings: Settings, spider_class: type[Spider]):
    crawler_process = CrawlerProcess(settings, install_root_handler=False)
    crawler_process.crawl(spider_class)
    stats_collector = get_stats_collector(crawler_process)
    crawler_process.start()

    if reason := stats_collector.get_value("finish_reason"):
        if reason != "finished":
            raise RuntimeError(f"Scraping didn't finish properly, reason: {reason}")
    if item_count := stats_collector.get_value(
        "item_dropped_reasons_count/MissingRequiredFields"
    ):
        raise RuntimeError(
            f"Scraping failed with {item_count} items dropped because of missing required fields"
        )
    if exc_count := stats_collector.get_value("spider_exceptions"):
        raise RuntimeError(f"Scraping failed with {exc_count} exceptions raised")
    if error_count := stats_collector.get_value("log_count/ERROR"):
        raise RuntimeError(f"Scraping failed with {error_count} errors logged")


def get_stats_collector(crawler_process: CrawlerProcess) -> StatsCollector:
    if len(crawler_process.crawlers) != 1:
        raise RuntimeError("Exactly one crawler expected")
    crawler = crawler_process.crawlers.pop()
    return crawler.stats


class JobSpider(Spider):
    extra_item_pipelines = {
        "juniorguru_plucker.pipelines.required_fields_filter.Pipeline": 50,
        "juniorguru_plucker.pipelines.broken_encoding_filter.Pipeline": 100,
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
