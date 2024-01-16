from pathlib import Path
from typing import Generator, Type

import nest_asyncio
from apify import Actor
from scrapy import Spider
from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from scrapy.utils.reactor import install_reactor


async def run_actor(settings: Settings, spider_class: Type[Spider]) -> None:
    async with Actor:
        Actor.log.info(f"Spider {spider_class.name}")
        actor_input = await Actor.get_input() or {}
        proxy_config = actor_input.get("proxyConfig")
        settings = apply_apify_settings(settings, proxy_config=proxy_config)
        crawler = CrawlerProcess(settings, install_root_handler=False)

        Actor.log.info("Importing spider")
        crawler.crawl(spider_class)

        Actor.log.info("Starting spider")
        crawler.start()


def apply_apify_settings(
    settings: Settings, proxy_config: dict | None = None
) -> Settings:
    # Use ApifyScheduler as the scheduler
    settings["SCHEDULER"] = "apify.scrapy.scheduler.ApifyScheduler"

    # Add the ActorDatasetPushPipeline into the item pipelines, assigning it the highest integer (1000),
    # ensuring it is executed as the final step in the pipeline sequence
    settings["ITEM_PIPELINES"]["apify.scrapy.pipelines.ActorDatasetPushPipeline"] = 1000

    # Disable the default RobotsTxtMiddleware, Apify's custom scheduler already handles robots.txt
    settings["DOWNLOADER_MIDDLEWARES"][
        "scrapy.downloadermiddlewares.robotstxt.RobotsTxtMiddleware"
    ] = None

    # Disable the default HttpProxyMiddleware and add ApifyHttpProxyMiddleware
    settings["DOWNLOADER_MIDDLEWARES"][
        "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware"
    ] = None
    settings["DOWNLOADER_MIDDLEWARES"][
        "apify.scrapy.middlewares.ApifyHttpProxyMiddleware"
    ] = 950

    # Disable the default RetryMiddleware and add ApifyRetryMiddleware with the highest integer (1000)
    settings["DOWNLOADER_MIDDLEWARES"][
        "scrapy.downloadermiddlewares.retry.RetryMiddleware"
    ] = None
    settings["DOWNLOADER_MIDDLEWARES"][
        "apify.scrapy.middlewares.ApifyRetryMiddleware"
    ] = 1000

    # Store the proxy configuration
    settings["APIFY_PROXY_SETTINGS"] = proxy_config

    return settings


def configure_async():
    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
    nest_asyncio.apply()


def iter_actor_paths(path: Path) -> Generator[Path, None, None]:
    for actor_spec in path.rglob(".actor/actor.json"):
        yield actor_spec.parent.parent
