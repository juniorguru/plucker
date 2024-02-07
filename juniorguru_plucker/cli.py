import logging
import sys

from apify_client import ApifyClient
from apify_shared.consts import ActorJobStatus
from scrapy.utils.project import get_project_settings

from juniorguru_plucker.loggers import configure_logging


settings = get_project_settings()
configure_logging(settings, sys.argv)


# ruff: noqa: E402
import asyncio
import importlib
import json
from pathlib import Path

import click
from scrapy import Item

from juniorguru_plucker.actors import (
    configure_async,
    generate_schema,
    get_spider_module_name,
    iter_actor_paths,
    run_actor,
)
from juniorguru_plucker.spiders import run_spider


logger = logging.getLogger("juniorguru_plucker")


@click.group()
@click.option("-d", "--debug", default=False, is_flag=True)
def main(debug: bool = False):
    pass  # --debug is processed in configure_logging()


@main.command()
@click.argument("spider_name", type=str, required=False)
@click.option(
    "--actor",
    "actor_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    envvar="ACTOR_PATH_IN_DOCKER_CONTEXT",
)
@click.option("--apify/--no-apify", default=False)
def crawl(
    spider_name: str | None = None,
    actor_path: str | None | Path = None,
    apify: bool = False,
):
    if spider_name:
        if actor_path:
            logger.warning(
                "Both spider_name and actor_path specified, actor_path will be ignored!"
            )
        spider_package_name = spider_name.replace("-", "_")
        actor_path = f"juniorguru_plucker/{spider_package_name}"
        spider_module_name = f"juniorguru_plucker.{spider_package_name}.spider"
    elif actor_path:
        # e.g. juniorguru_plucker/exchange_rates
        spider_module_name = get_spider_module_name(actor_path)
    else:
        raise click.BadParameter("Either spider_name or actor_path must be specified")

    logger.info(f"Importing spider from {spider_module_name!r}")
    spider_class = importlib.import_module(spider_module_name).Spider

    configure_async()
    if apify:
        logger.info(f"Crawling as Apify actor {actor_path!r}")
        actor_path = Path(actor_path)
        if not (actor_path / ".actor/actor.json").is_file():
            actors = ", ".join([str(path) for path in iter_actor_paths(".")])
            raise click.BadParameter(
                f"Actor {actor_path} not found! Valid actors: {actors}"
            )
        asyncio.run(run_actor(settings, spider_class))
    else:
        logger.info(f"Crawling as Scrapy spider {spider_name!r}")
        run_spider(settings, spider_class)


@main.command()
@click.argument("items_module_name", default="juniorguru_plucker.items", type=str)
@click.argument(
    "output_path",
    default="juniorguru_plucker/schemas",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def schemas(items_module_name: str, output_path: Path, do_print: bool = False):
    items_module = importlib.import_module(items_module_name)

    for member_name in dir(items_module):
        member = getattr(items_module, member_name)
        if not isinstance(member, type):
            continue
        if not issubclass(member, Item):
            continue
        if member == Item:
            continue
        logger.info(f"Generating schema for {member_name}…")
        schema = generate_schema(member)

        schema_name = member_name[0].lower() + member_name[1:]
        schema_path = output_path / f"{schema_name}Schema.json"
        schema_path.write_text(json.dumps(schema, indent=4, ensure_ascii=False) + "\n")


@main.command()
@click.option("--token", envvar="APIFY_TOKEN", required=True)
@click.option(
    "--git-repo-url",
    "git_repo_url_match",
    default="https://github.com/juniorguru/plucker#main",
)
def build(token: str, git_repo_url_match: str):
    client = ApifyClient(token=token)
    for actor_info in client.actors().list(my=True).items:
        logger.info(f"Actor {actor_info['username']}/{actor_info['name']}")
        actor_client = client.actor(actor_info["id"])
        if actor := actor_client.get():
            try:
                latest_version = actor["versions"][0]
            except IndexError:
                logger.warning("No versions found")
                raise click.Abort()

            git_repo_url = latest_version.get("gitRepoUrl") or ""
            if git_repo_url.startswith(git_repo_url_match):
                logger.info("Building actor…")
                actor_client.build(
                    version_number=latest_version["versionNumber"],
                    wait_for_finish=60,
                )
            else:
                logger.warning("Not a plucker actor")
        else:
            logger.error(f"Actor {actor_info['id']} not found")
            raise click.Abort()


@main.command()
@click.option("--token", envvar="APIFY_TOKEN", required=True)
def check(token: str):
    client = ApifyClient(token=token)
    for actor_info in client.actors().list().items:
        logger.info(f"Actor {actor_info['username']}/{actor_info['name']}")
        actor_client = client.actor(actor_info["id"])

        last_run = actor_client.last_run()
        run_info = last_run.get()
        if run_info is None:
            logger.warning("No runs found")
        elif run_info["status"] == ActorJobStatus.SUCCEEDED:
            logger.info(f"Status: {run_info['status']}, {run_info['startedAt']}")
        else:
            logger.error(f"Status: {run_info['status']}, {run_info['startedAt']}")
            raise click.Abort()
