"""Crawls a single URL with the job-logos spider and prints stats as JSON

Runs in a subprocess, because the Twisted reactor can't be restarted.
Usage: python crawl.py URL
"""

import json
import sys

from scrapy import signals
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from jg.plucker.job_logos.spider import Spider


def main(url: str) -> None:
    settings = get_project_settings()
    settings.setdict({"HTTPCACHE_ENABLED": False, "FEEDS": {}}, priority="cmdline")

    # Spider settings have priority over project settings, so patch them
    Spider.custom_settings = (Spider.custom_settings or {}) | {"DOWNLOAD_TIMEOUT": 1}

    items = []

    def item_scraped(item: dict) -> None:
        items.append(item)

    process = CrawlerProcess(settings, install_root_handler=False)
    crawler = process.create_crawler(Spider)
    crawler.signals.connect(item_scraped, signal=signals.item_scraped)
    process.crawl(crawler, links=[{"url": url}])
    process.start()

    stats = crawler.stats.get_stats()
    print(
        json.dumps(
            {
                "stats": {k: v for k, v in stats.items() if isinstance(v, int)},
                "items_count": len(items),
            }
        )
    )


if __name__ == "__main__":
    main(sys.argv[1])
