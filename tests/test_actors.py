from pathlib import Path

from scrapy import Field, Item

from juniorguru_plucker.actors import generate_schema, get_spider_module_name


def test_get_spider_module():
    assert (
        get_spider_module_name("juniorguru_plucker/exchange_rates")
        == "juniorguru_plucker.exchange_rates.spider"
    )


def test_get_spider_module_path():
    assert (
        get_spider_module_name(Path("juniorguru_plucker/exchange_rates"))
        == "juniorguru_plucker.exchange_rates.spider"
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
