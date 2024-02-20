import html
import json
import time
from datetime import date, datetime
from typing import Any, Generator

import extruct
import feedparser
from itemloaders.processors import Identity, MapCompose, TakeFirst
from lxml import etree
from scrapy import Request, Spider as BaseSpider
from scrapy.http import HtmlResponse, XmlResponse
from scrapy.loader import ItemLoader

from juniorguru_plucker.items import Job
from juniorguru_plucker.processors import absolute_url


class Spider(BaseSpider):
    name = "jobs-test"

    start_urls = [
        "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
        "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    ]

    def parse(self, response: XmlResponse) -> Generator[Request, None, None]:
        for entry in feedparser.parse(response.text).entries:
            feed_data = dict(
                title=entry.title,
                posted_on=parse_struct_time(entry.published_parsed),
                company_logo_urls=[
                    c["url"] for c in getattr(entry, "media_content", [])
                ],
                description_html=entry.summary,
                remote=True,
                source_urls=response.url,
            )
            yield response.follow(
                entry.link, callback=self.parse_job, cb_kwargs=dict(feed_data=feed_data)
            )

    def parse_job(
        self, response: HtmlResponse, feed_data: dict[str, Any]
    ) -> Generator[Job, None, None]:
        loader = Loader(item=Job(), response=response)
        loader.add_value("url", response.url)

        for key, value in feed_data.items():
            loader.add_value(key, value)

        try:
            data = extract_job_posting(response.text, response.url)
        except (ValueError, json.JSONDecodeError, etree.ParserError):
            self.logger.warning("Failed to extract job posting", exc_info=True)
        else:
            loader.add_value("source", self.name)
            loader.add_value("source_urls", response.url)
            loader.add_value("title", data["title"])
            loader.add_value("posted_on", data["datePosted"])
            loader.add_value("description_html", html.unescape(data["description"]))
            loader.add_value("company_logo_urls", data.get("image"))
            loader.add_value("employment_types", [data["employmentType"]])
            loader.add_value("company_name", data["hiringOrganization"]["name"])
            loader.add_value("company_url", data["hiringOrganization"]["sameAs"])
            loader.add_value("locations_raw", data["hiringOrganization"]["address"])
            yield loader.load_item()


def parse_struct_time(struct_time: time.struct_time | None) -> date | None:
    if struct_time:
        return datetime.fromtimestamp(time.mktime(struct_time)).date()


def parse_date(value: str | None) -> date | None:
    if isinstance(value, date):
        return value
    if value:
        return date.fromisoformat(value[:10])


def extract_job_posting(html_string: str, base_url: str) -> dict[str, Any]:
    data = extruct.extract(html_string, base_url, syntaxes=["json-ld"])
    try:
        return [
            data_item
            for data_item in data["json-ld"]
            if data_item["@type"] == "JobPosting"
        ][0]
    except IndexError:
        raise ValueError("json-ld provided no job postings")


class Loader(ItemLoader):
    default_input_processor = MapCompose(str.strip)
    default_output_processor = TakeFirst()
    company_url_in = MapCompose(absolute_url)
    posted_on_in = MapCompose(parse_date)
    company_logo_urls_out = Identity()
    remote_in = MapCompose(bool)
    locations_raw_out = Identity()
    source_urls_out = Identity()
