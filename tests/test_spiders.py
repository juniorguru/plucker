import json
from importlib import import_module
from pathlib import Path

import pytest
from scrapy import Spider
from scrapy.settings import Settings

from juniorguru_plucker.spiders import JobSpider


spider_packages = [
    spider_path.parent for spider_path in Path("juniorguru_plucker").rglob("spider.py")
]

assert len(spider_packages) > 0, "no spider packages found"


@pytest.mark.parametrize(
    "spider_package",
    [
        pytest.param(spider_package, id=spider_package.name)
        for spider_package in spider_packages
    ],
)
def test_actor_config_exists(spider_package: Path):
    actor_config_path = spider_package / ".actor/actor.json"

    assert actor_config_path.exists()


@pytest.mark.parametrize(
    "spider_package, spider_class, actor_config",
    [
        pytest.param(
            spider_package,
            import_module(f"juniorguru_plucker.{spider_package.name}.spider").Spider,
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


def test_job_spider_item_pipelines():
    settings = Settings({"ITEM_PIPELINES": {"AbcPipeline": 50}})
    JobSpider.update_settings(settings)

    assert len(settings.getdict("ITEM_PIPELINES")) > 1


def test_job_spider_item_pipelines_override():
    settings = Settings({"ITEM_PIPELINES": {"AbcPipeline": 50}})

    class SpecificJobSpider(JobSpider):
        custom_settings = {"ITEM_PIPELINES": {"XyzPipeline": 50}}

    SpecificJobSpider.update_settings(settings)

    assert settings.getdict("ITEM_PIPELINES") == {"XyzPipeline": 50}
