import html
from collections.abc import AsyncGenerator, Generator
from typing import Any, cast
from urllib.parse import urlencode, urlparse

from itemloaders.processors import Identity, MapCompose, TakeFirst
from scrapy import Request, Spider as BaseSpider
from scrapy.http import Response, TextResponse
from scrapy.loader import ItemLoader

from jg.plucker.items import Job
from jg.plucker.processors import parse_iso_date
from jg.plucker.scrapers import UnexpectedDataError


API_URL = "https://getjob.cz/api/jobs/board"

JOB_URL_TEMPLATE = "https://getjob.cz/prace/{slug}"

# Filters of the listing, as used by the 'IT a technologie' field on https://getjob.cz/prace
# The 'bezpripnuti' param turns off pinned jobs, which would repeat on every page
LISTING_PARAMS = {"obor": "IT a technologie", "bezpripnuti": "1"}

# The site's own filter for jobs with home office
REMOTE_LISTING_PARAMS = LISTING_PARAMS | {"ho": "ano"}

# Sources GetJob takes jobs from (zdroj.kod), which junior.guru gets from elsewhere
# or doesn't want
SKIPPED_SOURCES = {
    "startupjobs": "scraped by jobs-startupjobs",
    # An aggregator: its apply links go through a tracker, which doesn't let bots through,
    # so there's no telling which job board the job comes from, and it's likely one
    # junior.guru already scrapes. GetJob also marks its content as limited
    "careerjet": "aggregator, the original source is unknown",
}

# Sources GetJob takes jobs from (zdroj.kod), which junior.guru doesn't get otherwise
INCLUDED_SOURCES = {
    "mpsv": "Úřad práce ČR",
}

# Job boards junior.guru gets jobs from directly. Jobs applied to on any of these
# get skipped, no matter what GetJob says the source is
SKIPPED_DOMAINS = [
    "jobs.cz",
    "linkedin.com",
    "profesia.sk",
    "startupjobs.cz",
]

# GetJob code of the job type (uvazky) → employment type
EMPLOYMENT_TYPES = {
    "fulltime": "plný úvazek",
    "parttime": "částečný úvazek",
    "brigada": "brigáda",
    "staz": "stáž",
    "trainee": "trainee",
}

# GetJob code of the contract type (formy) → employment type
CONTRACT_TYPES = {
    "smlouva": None,  # pracovní smlouva, says nothing beyond the job type
    "zivnost": "živnost",
    "dohoda": "dohoda",
}

BULLET = "• "


class Spider(BaseSpider):
    """
    Reads the JSON API behind https://getjob.cz/prace. First goes through the listing
    filtered by home office to learn which jobs are remote, then through the whole
    listing, and fetches the detail of each job it keeps, because only the detail
    has the description
    """

    name = "jobs-getjob"

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._remote_ids: set[str] = set()

    async def start(self) -> AsyncGenerator[Request]:
        yield Request(
            get_listing_url(REMOTE_LISTING_PARAMS, 1),
            callback=self.parse_remote_listing,
            cb_kwargs={"page": 1},
        )

    def parse_remote_listing(self, response: Response, page: int) -> Generator[Request]:
        data = cast(TextResponse, response).json()
        self._remote_ids.update(job["id"] for job in parse_listing_jobs(data))
        if has_next_page(data):
            yield Request(
                get_listing_url(REMOTE_LISTING_PARAMS, page + 1),
                callback=self.parse_remote_listing,
                cb_kwargs={"page": page + 1},
            )
        else:
            self.logger.info(f"Remote jobs: {len(self._remote_ids)}")
            yield Request(
                get_listing_url(LISTING_PARAMS, 1),
                callback=self.parse,
                cb_kwargs={"page": 1},
            )

    def parse(self, response: Response, page: int = 1) -> Generator[Request]:
        data = cast(TextResponse, response).json()
        for job in parse_listing_jobs(data):
            try:
                skip_reason = get_skip_reason(job)
            except UnknownSourceError as e:
                # logged errors fail the run at the end, see AGENTS.md
                self.logger.error(f"{e}, skipping {job['slug']!r}")
                continue
            if skip_reason:
                self.logger.debug(f"Skipping {job['slug']!r}: {skip_reason}")
                continue
            yield Request(
                get_detail_url(job["slug"]),
                callback=self.parse_job,
                cb_kwargs={"remote": job["id"] in self._remote_ids},
            )
        if has_next_page(data):
            yield Request(
                get_listing_url(LISTING_PARAMS, page + 1),
                callback=self.parse,
                cb_kwargs={"page": page + 1},
            )

    def parse_job(self, response: Response, remote: bool) -> Generator[Job]:
        if response.status == 410:
            self.logger.warning(f"Job no longer active: {response.url}")
            return
        data = cast(TextResponse, response).json()
        yield load_job(data["nabidka"], remote, self.name, response.url)


class UnknownSourceError(UnexpectedDataError):
    pass


def get_listing_url(params: dict[str, str], page: int) -> str:
    return f"{API_URL}?{urlencode(params | {'strana': str(page)})}"


def get_detail_url(slug: str) -> str:
    return f"{API_URL}?{urlencode({'nabidka': slug})}"


def parse_listing_jobs(data: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(data.get("nabidky"), list):
        raise UnexpectedDataError(f"No jobs in the listing: {sorted(data.keys())}")
    return data["nabidky"]


def has_next_page(data: dict[str, Any]) -> bool:
    if not isinstance(data.get("ma_dalsi"), bool):
        raise UnexpectedDataError(
            f"No pagination in the listing: {data.get('ma_dalsi')!r}"
        )
    return data["ma_dalsi"]


def get_skip_reason(job: dict[str, Any]) -> str | None:
    """
    Returns why the job should be skipped, or None if it should be kept

    Raises UnknownSourceError for sources the scraper doesn't know about yet,
    so that someone decides whether junior.guru wants them.
    """
    if apply_url := get_apply_url(job["reakce"]):
        domain = urlparse(apply_url).netloc.lower()
        for skipped_domain in SKIPPED_DOMAINS:
            if domain == skipped_domain or domain.endswith(f".{skipped_domain}"):
                return f"applied to on {skipped_domain}"
    source_kind = job["zdroj"]["kind"]
    source_code = job["zdroj"]["kod"]
    if source_kind == "vlastni":
        return None
    if source_kind == "prevzato":
        if source_code in SKIPPED_SOURCES:
            return f"source {source_code!r}: {SKIPPED_SOURCES[source_code]}"
        if source_code in INCLUDED_SOURCES:
            return None
        raise UnknownSourceError(f"Unknown source {source_code!r}")
    raise UnexpectedDataError(f"Unknown kind of source: {source_kind!r}")


def get_apply_url(reaction: dict[str, Any]) -> str | None:
    if reaction["typ"] == "odkaz":
        return reaction["cil"]
    if reaction["typ"] == "email":
        return None
    raise UnexpectedDataError(f"Unknown type of reaction: {reaction['typ']!r}")


def get_employment_types(job_types: list[str], contract_types: list[str]) -> list[str]:
    employment_types = []
    for job_type in job_types:
        try:
            employment_types.append(EMPLOYMENT_TYPES[job_type])
        except KeyError:
            raise UnexpectedDataError(f"Unknown job type: {job_type!r}")
    for contract_type in contract_types:
        try:
            employment_type = CONTRACT_TYPES[contract_type]
        except KeyError:
            raise UnexpectedDataError(f"Unknown contract type: {contract_type!r}")
        if employment_type:
            employment_types.append(employment_type)
    return employment_types


def text_to_html(text: str) -> str:
    """
    Turns the plain text description into HTML

    Lines become paragraphs and runs of bulleted lines become lists. The bullet is
    either at the start of the line, or alone on a line before the item.
    """
    parts = []
    list_items = []
    lines = iter(line.strip() for line in text.splitlines())
    for line in lines:
        if line == BULLET.strip():
            line = BULLET + next(lines, "")
            if line == BULLET:
                raise UnexpectedDataError(f"Bullet without an item: {text!r}")
        if line.startswith(BULLET):
            list_items.append(f"<li>{html.escape(line.removeprefix(BULLET))}</li>")
            continue
        if list_items:
            parts.append(f"<ul>{''.join(list_items)}</ul>")
            list_items = []
        if line:
            parts.append(f"<p>{html.escape(line)}</p>")
    if list_items:
        parts.append(f"<ul>{''.join(list_items)}</ul>")
    return "\n".join(parts)


def load_job(job: dict[str, Any], remote: bool, source: str, source_url: str) -> Job:
    loader = Loader(item=Job())
    loader.add_value("source", source)
    loader.add_value("source_urls", source_url)
    loader.add_value("title", job["title"])
    loader.add_value("url", JOB_URL_TEMPLATE.format(slug=job["slug"]))
    loader.add_value("apply_url", get_apply_url(job["reakce"]))
    loader.add_value("company_name", job["company"])
    loader.add_value("locations_raw", job["location"])
    loader.add_value("remote", remote)
    loader.add_value(
        "employment_types", get_employment_types(job["uvazky"], job["formy"])
    )
    loader.add_value("posted_on", job["published_at"])
    loader.add_value("description_html", text_to_html(job["popis"]))
    return loader.load_item()


def empty_to_none(value: str) -> str | None:
    return value or None


class Loader(ItemLoader):
    default_input_processor = MapCompose(str.strip)
    default_output_processor = TakeFirst()
    employment_types_out = Identity()
    posted_on_in = MapCompose(parse_iso_date)
    remote_in = Identity()
    locations_raw_in = MapCompose(str.strip, empty_to_none)
    locations_raw_out = Identity()
    source_urls_out = Identity()
