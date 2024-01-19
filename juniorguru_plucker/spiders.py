from scrapy import Spider as BaseSpider
from scrapy.settings import Settings


class JobSpider(BaseSpider):
    @classmethod
    def update_settings(cls, settings: Settings):
        settings.setdict(
            {
                "ITEM_PIPELINES": {
                    "juniorguru_plucker.pipelines.required_fields_filter.Pipeline": 50,
                    "juniorguru_plucker.pipelines.short_description_filter.Pipeline": 100,
                    "juniorguru_plucker.pipelines.broken_encoding_filter.Pipeline": 150,
                    "juniorguru_plucker.pipelines.language_parser.Pipeline": 200,
                    "juniorguru_plucker.pipelines.language_filter.Pipeline": 250,
                },
            },
            priority="spider",
        )
        super().update_settings(settings)
