import importlib
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import IO, Callable, Generator, Type
from urllib.parse import quote

import click
from apify.scrapy import initialize_logging
from apify_client import ApifyClient
from apify_shared.consts import ActorJobStatus, ActorSourceType
from pydantic import BaseModel
from scrapy import Item

from jg.plucker.scrapers import (
    StatsError,
    generate_schema,
    get_spider_module_name,
    iter_actor_paths,
    run_as_actor,
    run_as_spider,
    start_reactor,
)


class BuildWaitStatus(BaseModel):
    attempt: int
    total_attempts: int
    status: ActorJobStatus

    def __str__(self) -> str:
        return f"{self.attempt}/{self.total_attempts}, {self.status}"


logger = logging.getLogger("jg.plucker")


@click.group()
@click.option("-d", "--debug", default=False, is_flag=True)
def main(debug: bool = False):
    initialize_logging()
    level = logging.DEBUG if debug else logging.INFO
    logging.getLogger().setLevel(level)
    logger.setLevel(level)
    for name in ["asyncio", "filelock", "crawlee", "websockets.client", "PIL"]:
        logging.getLogger(name).setLevel(logging.WARNING)


@main.command(context_settings={"ignore_unknown_options": True})
@click.argument("spider_name", type=str, required=False)
@click.option(
    "--actor",
    "actor_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    envvar="ACTOR_PATH_IN_DOCKER_CONTEXT",
)
@click.option("--apify/--no-apify", default=False)
@click.option(
    "--params",
    "spider_params_f",
    is_flag=False,
    flag_value=sys.stdin,
    type=click.File("r"),
)
def crawl(
    spider_name: str | None = None,
    actor_path: str | None | Path = None,
    apify: bool = False,
    spider_params_f: IO | None = None,
):
    spider_module_name, actor_path = get_scraper(spider_name, actor_path)
    logger.info(f"Importing spider from {spider_module_name!r}")
    spider_class = importlib.import_module(spider_module_name).Spider

    if spider_params_f is None:
        spider_params = {}
    else:
        logger.info("Reading spider params from stdin")
        spider_params = json.load(spider_params_f)

    try:
        if apify:
            logger.info(f"Crawling as Apify actor {actor_path}")
            if not (actor_path / ".actor/actor.json").is_file():
                actors = ", ".join([str(path) for path in iter_actor_paths(".")])
                raise click.BadParameter(
                    f"Actor {actor_path} not found! Valid actors: {actors}"
                )
            run = run_as_actor(spider_class, spider_params)
        else:
            logger.info(f"Crawling as Scrapy spider {spider_name!r}")
            run = run_as_spider(spider_class, spider_params)
        start_reactor(run)
    except StatsError as e:
        logger.error(e)
        raise click.Abort()


@main.command()
@click.argument("items_module_name", default="jg.plucker.items", type=str)
@click.argument(
    "output_path",
    default="src/jg/plucker/schemas",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def schemas(items_module_name: str, output_path: Path):
    for item_type in item_types(items_module_name):
        item_type_name = item_type.__name__
        logger.info(f"Generating schema for {item_type_name}…")
        schema = generate_schema(item_type)

        schema_name = item_type_name[0].lower() + item_type_name[1:]
        schema_path = output_path / f"{schema_name}Schema.json"
        schema_path.write_text(json.dumps(schema, indent=4, ensure_ascii=False) + "\n")


@main.command()
@click.option("--token", envvar="APIFY_TOKEN", required=True)
@click.option(
    "--git-repo-url",
    "git_repo_url_match",
    default="https://github.com/juniorguru/plucker#main",
)
@click.option("--build-timeout", default=5 * 60, type=int, help="In seconds.")
@click.option("--build-polling-wait", default=30, type=int, help="In seconds.")
@click.option("--build-attempts", default=2, type=int)
def build(
    token: str,
    git_repo_url_match: str,
    build_timeout: int,
    build_polling_wait: int,
    build_attempts: int,
):
    client = ApifyClient(token=token)
    success = False
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
                for attempt in range(1, build_attempts + 1):
                    logger.info(f"Building actor… (attempt #{attempt})")
                    build_info = actor_client.build(
                        version_number=latest_version["versionNumber"]
                    )
                    build = client.build(build_info["id"])
                    try:
                        for status in wait_for_build_status(
                            build.get, build_timeout, build_polling_wait
                        ):
                            logger.info(f"Waiting for build to finish… ({status})")
                        if not success:
                            logger.info("Good, the plucker repo can be built")
                            success = True
                        break
                    except RuntimeError as e:
                        logger.error(str(e))
                        if success and attempt == 1:
                            logger.info(
                                "The plucker repo can be built, but this build failed. Retrying…"
                            )
                        else:
                            raise click.Abort()
            else:
                logger.warning("Not a plucker actor")
        else:
            logger.error(f"Actor {actor_info['id']} not found")
            raise click.Abort()


@main.command()
@click.option("--token", envvar="APIFY_TOKEN", required=True)
@click.option(
    "-l",
    "--lookback",
    default=2,
    type=int,
    help="How many previous runs to consider in the decision.",
)
def check(token: str, lookback: int):
    client = ApifyClient(token=token)
    schedules = [
        schedule
        for schedule in client.schedules().list().items
        if schedule["isEnabled"]
    ]
    logger.info(f"Found {len(schedules)} enabled schedules")

    actor_ids = set()
    for schedule in schedules:
        schedule_actor_ids = [
            action["actorId"]
            for action in schedule["actions"]
            if action["type"] == "RUN_ACTOR"
        ]
        logger.info(
            f"{schedule['title']}\n"
            f"· actors: {len(schedule_actor_ids)}\n"
            f"· cron: {schedule['cronExpression']}\n"
            f"· last: {schedule['lastRunAt']:%Y-%m-%d %H:%I} UTC\n"
            f"· next: {schedule['nextRunAt']:%Y-%m-%d %H:%I} UTC"
        )
        actor_ids.update(schedule_actor_ids)
    logger.info(f"Found {len(actor_ids)} scheduled actors")

    logs_urls = []
    for actor_id in actor_ids:
        actor_client = client.actor(actor_id)
        if actor_info := actor_client.get():
            actor_name = f"{actor_info['username']}/{actor_info['name']}"
            logger.debug(f"Actor {actor_name}")
            runs = actor_client.runs()
            latest_runs = runs.list(limit=lookback, desc=True).items
            latest_runs_count = len(latest_runs)
            successful_runs_count = len(
                [
                    run
                    for run in latest_runs
                    if run["status"] == ActorJobStatus.SUCCEEDED
                ]
            )
            if successful_runs_count == latest_runs_count:
                logger.info(
                    f"{actor_name}: {successful_runs_count}/{latest_runs_count} successful"
                )
            elif successful_runs_count:
                logger.warning(
                    f"{actor_name}: {successful_runs_count}/{latest_runs_count} successful"
                )
            else:
                logger.error(f"{actor_name}: No successful runs found")
                logs_urls.append(f"https://console.apify.com/actors/{actor_id}/runs/")
        else:
            logger.error(f"Actor {actor_id!r} not found")
            raise click.Abort()

    if logs_urls:
        logger.error(
            f"Found {len(logs_urls)} actors which didn't succeed:\n"
            + "\n".join([f"· {logs_url}" for logs_url in logs_urls])
        )
        raise click.Abort()
    else:
        logger.info("All good!")


@main.command()
@click.argument("items_module_name", default="jg.plucker.items", type=str)
def new(items_module_name: str):
    try:
        from cookiecutter.main import cookiecutter
    except ImportError:
        logger.error("Cookiecutter not installed")
        raise click.Abort()
    item_name_choices = sorted(
        item_type.__name__ for item_type in item_types(items_module_name)
    )
    cookiecutter(
        ".",
        directory="scraper_template",
        output_dir="src/jg/plucker",
        extra_context={"item_name": item_name_choices},
    )
    subprocess.run(["ruff", "check", "--fix", "--quiet"], check=True)
    subprocess.run(["ruff", "format", "--quiet"], check=True)


@main.command()
@click.option("--token", envvar="APIFY_TOKEN", required=True)
@click.option(
    "--git-repo-url",
    default="https://github.com/juniorguru/plucker#main",
)
@click.option("--overwrite", default=False, is_flag=True)
@click.option("--build/--no-build", default=True)
@click.option("--version", default="0.0")
@click.argument("spider_name", type=str, required=False)
@click.option(
    "--actor",
    "actor_path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
def deploy(
    token: str,
    git_repo_url: str,
    overwrite: bool,
    build: bool,
    version: str,
    spider_name: str | None = None,
    actor_path: str | None | Path = None,
):
    client = ApifyClient(token=token)
    _, actor_path = get_scraper(spider_name, actor_path)
    actor_config = json.loads((actor_path / ".actor/actor.json").read_text())

    try:
        actor_id = [
            actor_info["id"]
            for actor_info in client.actors().list().items
            if actor_info["name"] == actor_config["name"]
        ][0]
    except IndexError:
        if overwrite:
            logger.info(f"Actor {actor_config['name']} not found, nothing to overwrite")
    else:
        if overwrite:
            logger.warning(f"Deleting actor {actor_config['name']}…")
            client.actor(actor_id).delete()
        else:
            logger.error(f"Actor {actor_config['name']} already exists")
            raise click.Abort()

    actor_info = client.actors().create(
        name=actor_config["name"],
        title=actor_config["title"],
        versions=[
            dict(
                versionNumber=version,
                sourceType=ActorSourceType.GIT_REPO,
                gitRepoUrl=f"{git_repo_url}:{actor_path}",
            )
        ],
        is_public=False,
    )
    logger.info(f"Actor {actor_info['name']} created: {actor_info['id']}")

    if build:
        logger.info(f"Building actor {actor_info['name']}…")
        build_info = client.actor(actor_info["id"]).build(
            version_number=version, wait_for_finish=60 * 5
        )
        if build_info["status"] != ActorJobStatus.SUCCEEDED:
            logger.error(f"Status: {build_info['status']}")
            raise click.Abort()


@main.command()
def li_params():
    search_queries = [
        "junior software engineer",
        "junior developer",
        "junior vyvojar",
        "junior programator",
        "junior tester",
        "junior data",
    ]
    locations = [
        ("Czechia", "104508036"),
        ("Slovakia", "103119917"),
    ]
    urls = [
        (
            f"https://www.linkedin.com/jobs/search"
            f"?keywords={quote(query)}"
            f"&location={quote(location)}"
            f"&geoId={geo_id}"
            f"&f_TPR=r86400"  # last 24 hours
            f"&position=1"
            f"&pageNum=0"
        )
        for query in search_queries
        for location, geo_id in locations
    ]
    params = {"count": 1000, "scrapeCompany": True, "urls": urls}
    click.echo(json.dumps(params, indent=2, ensure_ascii=False))


def get_scraper(
    spider_name: str | None = None,
    actor_path: str | Path | None = None,
) -> tuple[str, Path]:
    if spider_name:
        if actor_path:
            logger.warning(
                "Both spider_name and actor_path specified, actor_path will be ignored!"
            )
        spider_package_name = spider_name.replace("-", "_")
        actor_path = Path(f"src/jg/plucker/{spider_package_name}")
        return (f"jg.plucker.{spider_package_name}.spider", actor_path)
    if actor_path:
        # e.g. src/jg/plucker/exchange_rates
        return (get_spider_module_name(actor_path), Path(actor_path))
    raise click.BadParameter("Either spider_name or actor_path must be specified")


def item_types(items_module_name: str) -> Generator[Type[Item], None, None]:
    items_module = importlib.import_module(items_module_name)
    for member_name in dir(items_module):
        member = getattr(items_module, member_name)
        if not isinstance(member, type):
            continue
        if not issubclass(member, Item):
            continue
        if member == Item:
            continue
        yield member


def wait_for_build_status(
    get_build_info: Callable, build_timeout: int, build_polling_wait: int
) -> Generator[BuildWaitStatus, None, None]:
    total_attempts = build_timeout // build_polling_wait
    time.sleep(build_polling_wait)
    for attempt in range(1, total_attempts):
        build_info = get_build_info()
        if build_info is None:
            raise RuntimeError("Build not found")
        if build_info["status"] in [ActorJobStatus.SUCCEEDED, ActorJobStatus.FAILED]:
            break
        yield BuildWaitStatus(
            attempt=attempt,
            total_attempts=total_attempts,
            status=build_info["status"],
        )
        time.sleep(build_polling_wait)
    if build_info["status"] != ActorJobStatus.SUCCEEDED:
        raise RuntimeError(f"Build status: {build_info['status']}")
