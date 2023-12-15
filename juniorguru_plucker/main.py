# This module defines the main coroutine for the Apify Scrapy Actor, executed from the __main__.py file. The coroutine
# processes the Actor's input and executes the Scrapy spider. Additionally, it configures Scrapy project settings by
# adding Apify custom components, including a custom scheduler, retry middleware, and an item pipeline for pushing
# data to the Apify dataset.
#
# If you need to execute a coroutine within the Spider, it's recommended to use Apify's custom
# nested event loop. See the code example below or find inspiration from Apify's Scrapy components, such as
# [ApifyScheduler](https://github.com/apify/apify-sdk-python/blob/v1.3.0/src/apify/scrapy/scheduler.py#L109).
#
# ```
# from apify.scrapy.utils import nested_event_loop
#
# nested_event_loop.run_until_complete(my_coroutine())
# ```

import importlib
import os
from pathlib import Path

from scrapy.crawler import CrawlerProcess
from scrapy.settings import Settings
from scrapy.utils.project import get_project_settings
from apify import Actor


def apply_apify_settings(settings: Settings) -> Settings:
    # Add the ActorDatasetPushPipeline into the item pipelines, assigning it the highest integer (1000),
    # ensuring it is executed as the final step in the pipeline sequence
    settings['ITEM_PIPELINES']['apify.scrapy.pipelines.ActorDatasetPushPipeline'] = 1000

    # Disable the default RetryMiddleware and add ApifyRetryMiddleware with the highest integer (1000)
    settings['DOWNLOADER_MIDDLEWARES']['scrapy.downloadermiddlewares.retry.RetryMiddleware'] = None
    settings['DOWNLOADER_MIDDLEWARES']['apify.scrapy.middlewares.ApifyRetryMiddleware'] = 1000

    # Use ApifyScheduler as the scheduler
    settings['SCHEDULER'] = 'apify.scrapy.scheduler.ApifyScheduler'

    return settings


async def main() -> None:
    actor_path = os.environ['ACTOR_PATH_IN_DOCKER_CONTEXT']  # e.g. juniorguru_plucker/jobs_startupjobs
    spider_module_name = f"{actor_path.replace('/', '.')}.spider"

    async with Actor:
        Actor.log.info(f'Actor {actor_path} is being executed…')
        settings = apply_apify_settings(get_project_settings())
        crawler = CrawlerProcess(settings, install_root_handler=False)
        Actor.log.info(f"Actor's spider: {spider_module_name}")
        crawler.crawl(importlib.import_module(spider_module_name).Spider)
        crawler.start()
