"""Crawls with a spider adding a downloader middleware, prints the middlewares as JSON

Runs in a subprocess, because the Twisted reactor can't be restarted.
Usage: python crawl_settings.py
"""

import json
from collections.abc import AsyncGenerator

from scrapy import Request, Spider as BaseSpider
from scrapy.settings import BaseSettings

from jg.plucker.scrapers import crawl, get_actor_settings, start_reactor


class Middleware:
    pass


class Spider(BaseSpider):
    name = "test"

    @classmethod
    def update_settings(cls, settings: BaseSettings) -> None:
        super().update_settings(settings)
        settings["DOWNLOADER_MIDDLEWARES"].set(
            "__main__.Middleware", 1000, priority="spider"
        )

    async def start(self) -> AsyncGenerator[Request]:
        return
        yield


async def main() -> None:
    settings = get_actor_settings({"useApifyProxy": True})
    settings["HTTPCACHE_ENABLED"] = False
    crawler = await crawl(settings, Spider, {})
    print(json.dumps(dict(crawler.settings["DOWNLOADER_MIDDLEWARES"])))


if __name__ == "__main__":
    start_reactor(main())
