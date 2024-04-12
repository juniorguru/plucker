import json
from pathlib import Path

import pytest
from scrapy import Item

from jg.plucker import items
from jg.plucker.actors import generate_schema


items_module_members = [getattr(items, name) for name in dir(items)]

item_classes = [
    member
    for member in items_module_members
    if isinstance(member, type) and issubclass(member, Item) and member != Item
]

assert len(item_classes) > 0, f"no item classes found in {items.__file__}"


@pytest.mark.parametrize(
    "item_class",
    [pytest.param(item_class, id=item_class.__name__) for item_class in item_classes],
)
def test_schema_exists(item_class: type[Item]):
    item_class_name = item_class.__name__
    schema_name = item_class_name[0].lower() + item_class_name[1:]
    schema_path = Path(f"jg/plucker/schemas/{schema_name}Schema.json")

    assert schema_path.exists()


@pytest.mark.parametrize(
    "item_class",
    [pytest.param(item_class, id=item_class.__name__) for item_class in item_classes],
)
def test_schema_is_updated(item_class: type[Item]):
    item_class_name = item_class.__name__
    schema_name = item_class_name[0].lower() + item_class_name[1:]
    schema_path = Path(f"jg/plucker/schemas/{schema_name}Schema.json")

    assert json.loads(schema_path.read_text()) == generate_schema(item_class)
