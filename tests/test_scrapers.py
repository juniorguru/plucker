import json
from importlib import import_module
from pathlib import Path

import pytest
from scrapy import Field, Item, Spider

from jg.plucker.scrapers import (
    StatsError,
    evaluate_stats,
    generate_schema,
    get_spider_module_name,
)


spider_packages = [
    spider_path.parent for spider_path in Path("jg/plucker").rglob("spider.py")
]

assert len(spider_packages) > 0, "no spider packages found"


@pytest.mark.parametrize(
    "spider_package",
    [
        pytest.param(spider_package, id=spider_package.name)
        for spider_package in spider_packages
    ],
)
def test_actor_config_is_readable(spider_package: Path):
    actor_config_path = spider_package / ".actor/actor.json"

    assert json.loads(actor_config_path.read_text())


@pytest.mark.parametrize(
    "spider_package",
    [
        pytest.param(spider_package, id=spider_package.name)
        for spider_package in spider_packages
    ],
)
def test_actor_config_has_valid_docker_paths(spider_package: Path):
    actor_config_path = spider_package / ".actor/actor.json"
    actor_config = json.loads(actor_config_path.read_text())
    dockerfile_path = actor_config_path.parent / actor_config["dockerfile"]
    docker_context_path = actor_config_path.parent / actor_config["dockerContextDir"]

    assert dockerfile_path.read_text()
    assert dockerfile_path.parent == docker_context_path


@pytest.mark.parametrize(
    "spider_package",
    [
        pytest.param(spider_package, id=spider_package.name)
        for spider_package in spider_packages
    ],
)
def test_actor_config_has_valid_schema_path(spider_package: Path):
    actor_config_path = spider_package / ".actor/actor.json"
    actor_config = json.loads(actor_config_path.read_text())
    dataset_path = actor_config_path.parent / actor_config["storages"]["dataset"]

    assert json.loads(dataset_path.read_text())


@pytest.mark.parametrize(
    "spider_package, spider_class, actor_config",
    [
        pytest.param(
            spider_package,
            import_module(f"jg.plucker.{spider_package.name}.spider").Spider,
            json.loads((spider_package / ".actor/actor.json").read_text()),
            id=spider_package.name,
        )
        for spider_package in spider_packages
    ],
)
def test_spider_names(
    spider_package: Path, spider_class: type[Spider], actor_config: dict
):
    assert "-" not in spider_package.name
    assert spider_package.name.replace("_", "-") == spider_class.name

    assert "_" not in spider_class.name
    assert spider_class.name == actor_config["name"] == actor_config["title"]


def test_evaluate_stats_passing():
    evaluate_stats(
        {
            "item_scraped_count": 10,
            "finish_reason": "finished",
            "item_dropped_reasons_count/MissingRequiredFields": 0,
            "spider_exceptions": 0,
            "log_count/ERROR": 0,
        },
        min_items=10,
    )


@pytest.mark.parametrize(
    "stats_override",
    [
        {"item_scraped_count": 0},
        {"item_scraped_count": 5},
        {"finish_reason": "cancelled"},
        {"item_dropped_reasons_count/MissingRequiredFields": 1},
        {"spider_exceptions": 1},
        {"log_count/ERROR": 1},
    ],
)
def test_evaluate_stats_failing(stats_override: dict):
    with pytest.raises(StatsError):
        evaluate_stats(
            {
                "item_scraped_count": 10,
                "finish_reason": "finished",
                "item_dropped_reasons_count/MissingRequiredFields": 0,
                "spider_exceptions": 0,
                "log_count/ERROR": 0,
            }
            | stats_override,
            min_items=10,
        )


def test_evaluate_stats_min_items_passing():
    evaluate_stats(
        {
            "item_scraped_count": 7,
            "finish_reason": "finished",
            "item_dropped_reasons_count/MissingRequiredFields": 0,
            "spider_exceptions": 0,
            "log_count/ERROR": 0,
        },
        min_items=5,
    )


def test_evaluate_stats_min_items_passing_zero():
    evaluate_stats(
        {
            "item_scraped_count": 0,
            "finish_reason": "finished",
            "item_dropped_reasons_count/MissingRequiredFields": 0,
            "spider_exceptions": 0,
            "log_count/ERROR": 0,
        },
        min_items=0,
    )


def test_evaluate_stats_min_items_failing():
    with pytest.raises(StatsError):
        evaluate_stats(
            {
                "item_scraped_count": 10,
                "finish_reason": "finished",
                "item_dropped_reasons_count/MissingRequiredFields": 0,
                "spider_exceptions": 0,
                "log_count/ERROR": 0,
            },
            min_items=20,
        )


def test_get_spider_module():
    assert (
        get_spider_module_name("jg/plucker/exchange_rates")
        == "jg.plucker.exchange_rates.spider"
    )


def test_get_spider_module_path():
    assert (
        get_spider_module_name(Path("jg/plucker/exchange_rates"))
        == "jg.plucker.exchange_rates.spider"
    )


def test_generate_schema():
    class Bike(Item):
        name = Field()
        url = Field(apify_format="link")
        price = Field(apify_format="number")

    assert generate_schema(Bike) == {
        "title": "Bike",
        "actorSpecification": 1,
        "views": {
            "titles": {
                "title": "Bike",
                "transformation": {"fields": ["name", "price", "url"]},
                "display": {
                    "component": "table",
                    "properties": {
                        "name": {"label": "name"},
                        "price": {"label": "price", "format": "number"},
                        "url": {"label": "url", "format": "link"},
                    },
                },
            }
        },
    }
