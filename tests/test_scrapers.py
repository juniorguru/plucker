import asyncio
import json
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path

import pytest
from apify.storages import KeyValueStore
from scrapy import Field, Item, Request, Spider
from scrapy.http import HtmlResponse
from scrapy.settings import Settings
from scrapy.utils.test import get_crawler

from jg.plucker.scrapers import (
    RunCacheStorage,
    StatsError,
    evaluate_stats,
    generate_schema,
    get_closespider_timeout,
    get_spider_module_name,
)


spider_packages = [
    spider_path.parent for spider_path in Path("src/jg/plucker").rglob("spider.py")
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
            "spider_exceptions/count": 0,
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
        {"spider_exceptions/count": 1},
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
                "spider_exceptions/count": 0,
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
            "spider_exceptions/count": 0,
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
            "spider_exceptions/count": 0,
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
                "spider_exceptions/count": 0,
                "log_count/ERROR": 0,
            },
            min_items=20,
        )


def test_evaluate_stats_finish_reasons_passing():
    evaluate_stats(
        {"item_scraped_count": 10, "finish_reason": "closespider_timeout"},
        min_items=10,
        finish_reasons=["finished", "closespider_timeout"],
    )


def test_evaluate_stats_finish_reasons_failing():
    with pytest.raises(StatsError, match="closespider_timeout"):
        evaluate_stats(
            {"item_scraped_count": 10, "finish_reason": "closespider_timeout"},
            min_items=10,
        )


def test_get_closespider_timeout():
    now = datetime(2026, 10, 31, 4, 51, 28, tzinfo=UTC)
    timeout_at = now + timedelta(seconds=600)

    assert get_closespider_timeout(timeout_at, now) == 540


def test_get_closespider_timeout_no_timeout():
    now = datetime(2026, 10, 31, 4, 51, 28, tzinfo=UTC)

    assert get_closespider_timeout(None, now) is None


def test_get_closespider_timeout_little_time_left():
    now = datetime(2026, 10, 31, 4, 51, 28, tzinfo=UTC)
    timeout_at = now + timedelta(seconds=30)

    # zero would turn the timeout off
    assert get_closespider_timeout(timeout_at, now) == 1


def test_get_spider_module():
    assert (
        get_spider_module_name("src/jg/plucker/exchange_rates")
        == "jg.plucker.exchange_rates.spider"
    )


def test_get_spider_module_path():
    assert (
        get_spider_module_name(Path("src/jg/plucker/exchange_rates"))
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


def test_run_cache_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CRAWLEE_STORAGE_DIR", str(tmp_path))
    spider = Spider("test")
    spider.crawler = get_crawler(Spider)
    storage = RunCacheStorage(Settings({"HTTPCACHE_EXPIRATION_SECS": 0}))
    request = Request("https://example.com/")

    storage.open_spider(spider)
    try:
        assert storage.retrieve_response(spider, request) is None
        storage.store_response(
            spider,
            request,
            HtmlResponse(request.url, status=200, body=b"<html>Hello</html>"),
        )
        response = storage.retrieve_response(spider, request, current_time=2**31)
    finally:
        storage.close_spider(spider)

    assert response is not None
    assert response.status == 200
    assert response.body == b"<html>Hello</html>"
    assert list((tmp_path / "key_value_stores").iterdir()) == [
        tmp_path / "key_value_stores" / "httpcache"
    ]


def test_run_cache_storage_does_not_share_default_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # see https://github.com/juniorguru/plucker/issues/190
    monkeypatch.setenv("CRAWLEE_STORAGE_DIR", str(tmp_path))
    spider = Spider("test")
    spider.crawler = get_crawler(Spider)
    storage = RunCacheStorage(Settings({"HTTPCACHE_EXPIRATION_SECS": 0}))

    storage.open_spider(spider)
    try:
        default_kvs = asyncio.run(KeyValueStore.open())
        assert default_kvs is not storage._kvs
    finally:
        storage.close_spider(spider)
