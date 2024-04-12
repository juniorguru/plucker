import pytest
from scrapy import Field, Item, Spider

from jg.plucker.pipelines import (
    MissingRequiredFields,
    RequiredFieldsFilterPipeline,
)


class Something(Item):
    prop1 = Field()
    prop2 = Field(required=True)
    prop3 = Field()
    prop4 = Field(required=True)


def test_required_fields_filter_pipeline():
    item = Something(prop1="foo", prop2="moo", prop4="boo")
    RequiredFieldsFilterPipeline().process_item(item, Spider(name="sample"))


def test_required_fields_filter_pipeline_drops():
    item = Something()

    with pytest.raises(MissingRequiredFields, match="prop2, prop4"):
        RequiredFieldsFilterPipeline().process_item(item, Spider(name="sample"))
