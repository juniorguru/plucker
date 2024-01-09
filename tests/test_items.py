from pathlib import Path
import pytest
from scrapy import Item
from juniorguru_plucker import items


items_module_members = [getattr(items, name) for name in dir(items)]

item_classes = [
    member
    for member in items_module_members
    if isinstance(member, type) and issubclass(member, Item) and member != Item
]

assert len(item_classes) > 0, f"no item classes found in {items.__file__}"


@pytest.mark.parametrize("item_class", item_classes)
def test_schema_exists(item_class):
    item_class_name = item_class.__name__
    schema_name = item_class_name[0].lower() + item_class_name[1:]
    schema_path = Path(items.__file__).parent / f"{schema_name}Schema.json"

    assert schema_path.exists()
