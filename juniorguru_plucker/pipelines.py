from functools import lru_cache

from scrapy import Item, Spider
from scrapy.exceptions import DropItem


class MissingRequiredFields(DropItem):
    pass


class RequiredFieldsFilterPipeline:
    def process_item(self, item: Item, spider: Spider):
        required_fields = get_required_fields(item.__class__)
        missing_fields = required_fields - frozenset(item.keys())
        if missing_fields:
            missing_fields = sorted(missing_fields)
            raise MissingRequiredFields(f"Missing: {', '.join(missing_fields)}")
        return item


@lru_cache()
def get_required_fields(item_class: type[Item]) -> set[str]:
    return {
        name
        for name, kwargs in item_class.fields.items()
        if kwargs.get("required") is True
    }
