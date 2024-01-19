from scrapy import Spider as BaseSpider
from scrapy.settings import Settings


class JobSpider(BaseSpider):
    extra_item_pipelines = {
        "juniorguru_plucker.pipelines.required_fields_filter.Pipeline": 50,
        "juniorguru_plucker.pipelines.short_description_filter.Pipeline": 100,
        "juniorguru_plucker.pipelines.broken_encoding_filter.Pipeline": 150,
        "juniorguru_plucker.pipelines.language_parser.Pipeline": 200,
        "juniorguru_plucker.pipelines.language_filter.Pipeline": 250,
    }

    @classmethod
    def update_settings(cls, settings: Settings):
        if cls.custom_settings and "ITEM_PIPELINES" in cls.custom_settings:
            raise NotImplementedError(
                "Setting custom_settings['ITEM_PIPELINES'] not supported"
            )
        super().update_settings(settings)
        settings["ITEM_PIPELINES"].update(cls.extra_item_pipelines)
