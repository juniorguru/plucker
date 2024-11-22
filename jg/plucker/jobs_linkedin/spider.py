import json
import logging
import re
from datetime import datetime
from multiprocessing import Process, Queue
from pathlib import Path
from typing import Generator, cast
from urllib.parse import urlparse

from apify.log import ActorLogFormatter
from diskcache import Cache
from linkedin_api import Linkedin as BaseLinkedIn
from linkedin_api.client import ChallengeException
from scrapy import Request, Spider as BaseSpider
from scrapy.http import HtmlResponse
from twisted.python.failure import Failure

from jg.plucker.items import Job
from jg.plucker.url_params import (
    get_param,
    replace_in_params,
    strip_params,
    strip_utm_params,
)


class LinkedIn(BaseLinkedIn):
    def _fetch(self, uri: str, *args, **kwargs):
        # Patch which gives us more job data
        if uri.startswith("/jobs/jobPostings/"):
            kwargs["params"] = {
                "decorationId": "com.linkedin.voyager.deco.jobs.web.shared.WebFullJobPosting-64",
            }
        return super()._fetch(uri, *args, **kwargs)


class Spider(BaseSpider):
    # https://github.com/everping/Linkedin-Authentication-Challenge/tree/master
    # https://github.com/tomquirk/linkedin-api/issues/331
    # https://github.com/tomquirk/linkedin-api/issues/392
    # https://github.com/tomquirk/linkedin-api/issues/78

    name = "jobs-linkedin"

    cache_dir = Path.cwd() / ".linkedin_cache"

    cache_expire = 60 * 60 * 24

    search_queries = [
        "junior software engineer",
        "junior developer",
        "junior vyvojar",
        "junior programator",
        "junior tester",
        "junior data",
    ]

    locations = ["Czechia", "Slovakia"]

    start_url = "https://junior.guru"

    def start_requests(self) -> Generator[Request, None, None]:
        yield Request(self.start_url, self.parse, errback=self.handle_error)

    # This doesn't seem to work
    def handle_error(self, failure: Failure) -> Generator[Request, None, None]:
        self.logger.error(repr(failure))
        if "CHALLENGE" in failure.getErrorMessage():
            yield Request(
                self.start_url, self.parse, errback=self.handle_error, dont_filter=True
            )

    def parse(self, response: HtmlResponse) -> Generator[Job | Request, None, None]:
        queue = Queue()
        scrape_proc = Process(
            target=linkedin_task,
            args=(
                self.settings["LINKEDIN_USERNAME"],
                self.settings["LINKEDIN_PASSWORD"],
                queue,
                self.search_queries,
                self.locations,
                response.request.meta.get("proxy") if response.request else None,
                self.cache_dir,
                self.cache_expire,
                self.logger.name,
                self.logger.getEffectiveLevel(),
            ),
        )
        try:
            scrape_proc.start()
            while True:
                if job_data := queue.get():
                    if error := job_data.get("error"):
                        raise RuntimeError(error)
                    try:
                        yield create_job(job_data)
                    except NotImplementedError as e:
                        self.logger.warning(f"Failed to create job: {e}")
                    except Exception:
                        self.logger.error(
                            f"Failed to create job:\n\n"
                            f"{json.dumps(job_data, indent=2, ensure_ascii=False)}"
                        )
                        raise
                else:
                    break
        except Exception:
            self.logger.debug("Got exception, terminating task")
            scrape_proc.terminate()
            raise
        finally:
            scrape_proc.join()


def linkedin_task(
    username: str,
    password: str,
    queue: Queue,
    search_queries: list[str],
    locations: list[str],
    proxy: str | None,
    cache_dir: str | Path,
    cache_expire: int,
    logger_name: str,
    logger_level: int,
):
    if not username or not password:
        raise ValueError("Missing LinkedIn credentials")

    handler = logging.StreamHandler()
    handler.setFormatter(ActorLogFormatter(include_logger_name=True))
    logging.basicConfig(level=logger_level, handlers=[handler])
    logging.basicConfig = lambda *args, **kwargs: None
    logger = logging.getLogger(logger_name)

    try:
        logger.info(f"Proxy: {proxy}")
        api = LinkedIn(
            username,
            password,
            cookies_dir=f"{cache_dir}/",
            proxies={"http": proxy, "https": proxy},
            authenticate=True,
        )
        cache = Cache(Path(cache_dir) / "jobs")

        jobs = cast(list, cache.get("job-ids"))
        if not jobs:
            jobs = set()
            for search_query in search_queries:
                for location in locations:
                    logger.info(f"Searching for {search_query!r} @ {location}")
                    results = api.search_jobs(
                        search_query,
                        experience=["1", "2", "3"],
                        location_name=location,
                        listed_at=60 * 60 * 24 * 7 * 4,
                        distance=200,
                    )
                    jobs.update(
                        result["entityUrn"].split(":")[-1] for result in results
                    )
            jobs = sorted(jobs)
            cache.set("job-ids", jobs, expire=cache_expire)

        jobs_count = len(jobs)
        logger.info(f"Loaded {jobs_count} job IDs")

        for i, job_id in enumerate(jobs):
            logger.info(f"Job {get_job_url(job_id)} ({i + 1}/{jobs_count})")
            cache_key = f"job-{job_id}"
            job_data = cast(dict, cache.get(cache_key))
            if not job_data:
                logger.info("Fetching…")
                job_data = api.get_job(job_id)
                cache.set(cache_key, job_data, expire=cache_expire)
            queue.put(job_data)
    except BaseException as e:
        logger.exception(e)
        queue.put({"error": f"{e.__class__.__name__} / {e or '(no message)'}"})
    finally:
        queue.put(None)


def create_job(data: dict) -> Job:
    company_details = data["companyDetails"]
    try:
        company_wrapper = (
            company_details
            ["com.linkedin.voyager.deco.jobs.web.shared.WebJobPostingCompany"]
        )  # fmt: skip
    except KeyError:
        company_name = (
            company_details
            ["com.linkedin.voyager.jobs.JobPostingCompanyName"]
            ["companyName"]
        )  # fmt: skip
        logo_urls = []
    else:
        if "companyResolutionResult" not in company_wrapper:
            raise NotImplementedError("Company doesn't exist (anymore?)")
        company = company_wrapper["companyResolutionResult"]
        company_name = company["name"]
        try:
            logo = company["logo"]["image"]["com.linkedin.common.VectorImage"]
        except KeyError:
            logo_urls = []
        else:
            logo_urls = [
                logo["rootUrl"] + artifact["fileIdentifyingUrlPathSegment"]
                for artifact in logo["artifacts"]
            ]

    offsite_apply = data["applyMethod"].get("com.linkedin.voyager.jobs.OffsiteApply")
    if offsite_apply:
        apply_url = offsite_apply["companyApplyUrl"]
        apply_url = clean_url(clean_validated_url(clean_proxied_url(apply_url)))
    else:
        apply_url = None

    return Job(
        title=data["title"],
        posted_on=datetime.fromtimestamp(data["originalListedAt"] / 1e3),
        url=get_job_url(data["jobPostingId"]),
        apply_url=apply_url,
        company_name=company_name,
        company_logo_urls=logo_urls,
        locations_raw=data["formattedLocation"],
        remote=data["workRemoteAllowed"],
        employment_types=[data["employmentStatus"].split(":")[-1]],
        description_html=data["description"]["text"],
        source="linkedin",
        source_urls=[data["dashEntityUrn"]],
    )


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
