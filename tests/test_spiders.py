import json
from importlib import import_module
from pathlib import Path

import pytest
from scrapy import Spider
from scrapy.settings import Settings

from juniorguru_plucker.spiders import JobSpider as BaseJobSpider


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


def test_job_spider_extra_item_pipelines():
    settings = Settings({"ITEM_PIPELINES": {"APipeline": 50, "ApifyPipeline": 1000}})

    class JobsSpider(BaseJobSpider):
        extra_item_pipelines = {"BPipeline": 500}

    JobsSpider.update_settings(settings)

    assert settings.getdict("ITEM_PIPELINES") == {
        "APipeline": 50,
        "ApifyPipeline": 1000,
        "BPipeline": 500,
    }


def test_job_spider_item_custom_settings_item_pipelines():
    settings = Settings({"ITEM_PIPELINES": {"APipeline": 50}})

    class JobsSpider(BaseJobSpider):
        item_pipelines = {"BPipeline": 500}

    class SpecificJobSpider(JobsSpider):
        custom_settings = {"ITEM_PIPELINES": {"CPipeline": 50}}

    with pytest.raises(NotImplementedError):
        SpecificJobSpider.update_settings(settings)
