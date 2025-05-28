import hashlib
import logging

from apify import Actor
from scrapy import Item, Spider
from scrapy.exceptions import DropItem

from jg.plucker.items import get_image_fields, get_required_fields


logger = logging.getLogger("jg.plucker.pipelines")


class MissingRequiredFields(DropItem):
    pass


class RequiredFieldsFilterPipeline:
    def process_item(self, item: Item, spider: Spider) -> Item:
        required_fields = get_required_fields(item.__class__)
        missing_fields = required_fields - frozenset(item.keys())
        if missing_fields:
            missing_fields = sorted(missing_fields)
            raise MissingRequiredFields(f"Missing: {', '.join(missing_fields)}")
        return item


class ImagePipeline:
    def __init__(self):
        self._kvs = None

    async def process_item(self, item: Item, spider: Spider) -> Item:
        self._kvs = self._kvs or await Actor.open_key_value_store()
        item_class = item.__class__
        for field in get_image_fields(item_class):
            value = item[field]
            if isinstance(value, bytes):
                size_kb = len(value) // 1024
                logger.info(
                    f"Processing image: {item_class.__name__}.{field}, size {size_kb}kB, spider {spider.name}"
                )
                key = hashlib.sha256(value).hexdigest()
                await self._kvs.set_value(key, value)
                image_url = await self._kvs.get_public_url(key)
                logger.info(f"Image URL: {image_url}")
                item[field] = image_url
            else:
                logger.debug(
                    f"Skipping (not bytes): {item_class.__name__}.{field} with value {value!r}"
                )
        return item
