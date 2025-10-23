import re
from datetime import UTC, date, datetime, timedelta
from pprint import pformat
from typing import AsyncGenerator
from urllib.parse import quote, urlparse

from apify_client import ApifyClientAsync
from apify_shared.consts import ActorJobStatus
from scrapy import Spider as BaseSpider

from jg.plucker.items import Job
from jg.plucker.url_params import (
    get_param,
    replace_in_params,
    strip_params,
    strip_utm_params,
)


class Spider(BaseSpider):
    name = "jobs-linkedin"

    search_queries = [
        "junior software engineer",
        "junior developer",
        "junior vyvojar",
        "junior programator",
        "junior tester",
        "junior data",
    ]

    locations = [
        ("Czechia", "104508036"),
        ("Slovakia", "103119917"),
    ]

    async def start(self) -> AsyncGenerator[Job, None]:
        client = ApifyClientAsync(token=self.settings.get("APIFY_TOKEN"))
        li_actor = client.actor("curious_coder/linkedin-jobs-scraper")

        li_runs_listing = await li_actor.runs().list(
            status=ActorJobStatus.SUCCEEDED,
            desc=True,
            limit=1,
            started_after=datetime.now(UTC) - timedelta(hours=1),
        )
        if li_runs := li_runs_listing.items:
            li_run = li_runs[0]
            self.logger.info(
                f"Reusing LinkedIn scraper run from {li_run['startedAt']:%Y-%m-%d}: "
                f"{li_run['id']} (dataset {li_run['defaultDatasetId']})"
            )
            li_dataset = client.dataset(li_run["defaultDatasetId"])
        else:
            urls = [
                (
                    f"https://www.linkedin.com/jobs/search"
                    f"?keywords={quote(query)}"
                    f"&location={quote(location)}"
                    f"&geoId={geo_id}"
                    f"&f_TPR=r86400"  # last 24 hours
                    f"&position=1"
                    f"&pageNum=0"
                )
                for query in self.search_queries
                for location, geo_id in self.locations
            ]
            self.logger.info(f"Scraping {len(urls)} URLs:\n{pformat(urls)}")

            run_input = {"count": 1000, "scrapeCompany": True, "urls": urls}
            self.logger.debug(f"LinkedIn scraper input data:\n{pformat(run_input)}")
            self.logger.info("Starting the LinkedIn scraper actor...")
            li_run = await li_actor.call(run_input=run_input)
            if li_run:
                li_dataset = client.dataset(li_run["defaultDatasetId"])
            else:
                raise RuntimeError("Failed to call the LinkedIn scraper actor")
            self.logger.info("Scraping done!")

        items = (await li_dataset.list_items()).items
        items_count = len(items)
        self.logger.info(f"Processing {items_count} scraped items")

        for i, item in enumerate(items, start=1):
            if i % 100 == 0:
                self.logger.info(f"Processing item {i}/{items_count}")
            # self.logger.debug(f"LinkedIn scraper item:\n{pformat(item)}")
            apply_url = clean_url(
                clean_validated_url(clean_proxied_url(item["applyUrl"]))
            )
            yield Job(
                title=item["title"],
                posted_on=date.fromisoformat(item["postedAt"]),
                url=get_job_url(get_job_id(item["link"])),
                apply_url=apply_url or None,
                company_name=item["companyName"],
                company_url=item.get("companyWebsite"),
                company_logo_urls=[item["companyLogo"]],
                locations_raw=item["location"],
                employment_types=item["employmentType"],
                description_html=item["descriptionHtml"],
                source="linkedin",
                source_urls=[item["inputUrl"]],
            )
        self.logger.info("All items processed!")


def get_job_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}"


def get_job_id(url: str) -> str:
    if match := re.search(r"-(\d+)$", urlparse(url).path):
        return match.group(1)
    raise ValueError(f"Could not parse LinkedIn job ID: {url}")


def clean_proxied_url(url: str) -> str:
    proxied_url = get_param(url, "url")
    if proxied_url:
        proxied_url = strip_utm_params(proxied_url)
        return replace_in_params(
            proxied_url, "linkedin", "juniorguru", case_insensitive=True
        )
    return url


def clean_validated_url(url: str) -> str:
    if url and "validate.perfdrive.com" in url:
        if ssc_url := get_param(url, "ssc"):
            return ssc_url
        raise ValueError(f"Could not parse SSC URL: {url}")
    return url


def clean_url(url: str) -> str:
    if url and "linkedin.com" in url:
        return strip_params(url, ["refId", "trk", "trackingId"])
    if url and "talentify.io" in url:
        return strip_params(url, ["tdd"])
    if url and "neuvoo.cz" in url:
        return strip_params(url, ["puid"])
    if url and "lever.co" in url:
        return re.sub(r"/apply$", "/", url)
    url = strip_utm_params(url)
    url = replace_in_params(url, "linkedin", "juniorguru", case_insensitive=True)
    return url
