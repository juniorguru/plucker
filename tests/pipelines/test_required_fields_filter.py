import pytest
from scrapy import Field, Item, Spider

from juniorguru_plucker.pipelines.required_fields_filter import (
    MissingRequiredFields,
    Pipeline,
)


class Something(Item):
    prop1 = Field()
    prop2 = Field(required=True)
    prop3 = Field()
    prop4 = Field(required=True)


def test_required_fields_filter(spider: Spider):
    item = Something(prop1="foo", prop2="moo", prop4="boo")
    Pipeline().process_item(item, spider)


def test_required_fields_drops(spider: Spider):
    item = Something()

    with pytest.raises(MissingRequiredFields, match="prop2, prop4"):
        Pipeline().process_item(item, spider)
