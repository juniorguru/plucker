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
    print('ACTOR_PATH_IN_DOCKER_CONTEXT=', os.getenv('ACTOR_PATH_IN_DOCKER_CONTEXT'))

    async with Actor:
        Actor.log.info('Actor is being executed...')
        # actor_input = await Actor.get_input() or {}
        # spider_names = set(source for source in actor_input.get('sources', ['all']))

        # if 'all' in spider_names:
        #     for path in Path(__file__).parent.glob('spiders/*.py'):
        #         if path.stem != '__init__':
        #             spider_names.add(path.stem)
        #     spider_names.remove('all')
        spider_names = ['jobs_startupjobs']

        Actor.log.info(f"Executing spiders: {', '.join(spider_names)}")
        settings = apply_apify_settings(get_project_settings())
        crawler = CrawlerProcess(settings, install_root_handler=False)
        for spider_name in spider_names:
            spider_module_name = f"juniorguru_plucker.{spider_name}.spider"
            spider = importlib.import_module(spider_module_name)
            crawler.crawl(spider.Spider)
        crawler.start()
