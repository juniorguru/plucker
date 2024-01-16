import sys

from scrapy.utils.project import get_project_settings

from juniorguru_plucker.loggers import configure_logging


settings = get_project_settings()
configure_logging(settings, sys.argv)


# ruff: noqa: E402
import asyncio
import importlib
from pathlib import Path

import click

from juniorguru_plucker.actor import configure_async, iter_actor_paths, run_actor


@click.group()
@click.option("-d", "--debug", default=False, is_flag=True)
def main(debug: bool = False):
    pass


@main.command()
@click.argument("spider_name", type=str, required=False)
@click.argument(
    "actor_path",
    type=str,
    required=False,
    envvar="ACTOR_PATH_IN_DOCKER_CONTEXT",
)
def crawl(
    spider_name: str | None = None,
    actor_path: str | None | Path = None,
):
    if spider_name:
        actor_path = f"juniorguru_plucker/{spider_name}"
        spider_module_name = f"juniorguru_plucker.{spider_name}.spider"
    elif actor_path:
        # e.g. juniorguru_plucker/exchange_rates
        spider_module_name = f"{str(actor_path).replace('/', '.')}.spider"
    else:
        raise click.BadParameter("Either spider_name or actor_path must be specified")

    actor_path = Path(actor_path)
    if not (actor_path / ".actor/actor.json").is_file():
        actors = ", ".join(
            [str(path.relative_to(Path("."))) for path in iter_actor_paths(Path("."))]
        )
        raise click.BadParameter(
            f"Actor {actor_path} not found! Valid actors: {actors}"
        )

    # os.environ["SCRAPY_SETTINGS_MODULE"] = "juniorguru_plucker.settings"
    Spider = importlib.import_module(spider_module_name).Spider

    configure_async()
    asyncio.run(run_actor(settings, Spider))
