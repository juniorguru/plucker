from pathlib import Path
from typing import Generator, Type

import nest_asyncio
from apify import Actor
from apify.scrapy.utils import apply_apify_settings
from scrapy import Item, Spider
from scrapy.settings import BaseSettings, Settings
from scrapy.spiderloader import SpiderLoader as BaseSpiderLoader
from scrapy.utils.reactor import install_reactor

from juniorguru_plucker.spiders import run_spider


async def run_actor(settings: Settings, spider_class: Type[Spider]) -> None:
    async with Actor:
        Actor.log.info(f"Spider {spider_class.name}")
        actor_input = await Actor.get_input() or {}
        proxy_config = actor_input.get("proxyConfig")
        settings = apply_apify_settings(settings=settings, proxy_config=proxy_config)
        run_spider(settings, spider_class)


def configure_async():
    install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")
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
