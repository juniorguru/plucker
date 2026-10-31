import re
from collections import Counter
from collections.abc import AsyncGenerator, Generator
from typing import Any
from urllib.parse import urlparse

from scrapy import Request, Spider as BaseSpider, signals
from scrapy.crawler import Crawler
from scrapy.http.response import Response
from twisted.python.failure import Failure

from jg.plucker.items import JobCheck
from jg.plucker.jobs_jobscz.spider import (
    BETA_BUCKET_PROBE_URL,
    get_classic_site_cookie,
    is_beta_site,
)
from jg.plucker.jobs_profesiask.spider import (
    WAFChallengeError,
    get_gone_reason,
    raise_for_waf_challenge,
)
from jg.plucker.jobs_startupjobs.spider import EXPORT_URL as STARTUPJOBS_EXPORT_URL
from jg.plucker.scrapers import evaluate_stats, parse_links
from jg.plucker.settings import RETRY_HTTP_CODES


MIN_CHECKS_PER_HOST = 5

MAX_INCONCLUSIVE_RATIO = 0.5


class UnexpectedPageError(Exception):
    pass


class Spider(BaseSpider):
    name = "job-checks"

    custom_settings = {
        "HTTPCACHE_ENABLED": False,
        "HTTPERROR_ALLOW_ALL": True,
        # The run has a fixed time budget, and a blocked site would spend it all on retries
        "RETRY_TIMES": 3,
        "DOWNLOAD_TIMEOUT": 30,
        # Requests waiting for their site's download delay count towards the global
        # limit, so a throttled site would starve all the others. Rely on the limit
        # per site instead
        "CONCURRENT_REQUESTS": 1000,
        # AutoThrottle doesn't lower the delay on responses other than 200, so a site
        # responding with a WAF challenge would be checked at the start delay for good
        "AUTOTHROTTLE_START_DELAY": 1,
        # Each site gets ~120 links, and checking them one by one takes minutes,
        # e.g. profesia.sk redirects each link first, which doubles the requests
        "AUTOTHROTTLE_TARGET_CONCURRENCY": 4,
        "DUPEFILTER_CLASS": "scrapy.dupefilters.BaseDupeFilter",
        "METAREFRESH_ENABLED": False,
        # AWS WAF on profesia.sk challenges with an empty '202 Accepted'. Its '405' CAPTCHA
        # isn't retried, as 405 is a legit response to HEAD requests on other sites
        "RETRY_HTTP_CODES": [202] + RETRY_HTTP_CODES,
    }

    min_items = 0

    @classmethod
    def evaluate_stats(cls, stats: dict[str, Any], min_items: int) -> None:
        # Giving up on retries logs an error, but such links still get assessed
        # (as inconclusive), so it's not an error of the scraper
        max_retries = stats.get("retry/max_reached", 0)
        error_count = stats.get("log_count/ERROR", 0)
        stats_copy = stats.copy()
        stats_copy["log_count/ERROR"] = max(0, error_count - max_retries)
        return evaluate_stats(stats_copy, min_items)

    def __init__(
        self, name: str | None = None, links: list[dict[str, str]] | None = None
    ):
        super().__init__(name)
        parse_links(links)  # validates, but normalizes URLs, which wouldn't match
        self._start_urls = list(dict.fromkeys(link["url"] for link in links or []))
        self._expected_urls: set[str] = set()
        self._assessed_urls: set[str] = set()
        self._checks_by_host: Counter[str] = Counter()
        self._inconclusive_by_host: Counter[str] = Counter()

    @classmethod
    def from_crawler(cls, crawler: Crawler, *args: Any, **kwargs: Any) -> Spider:
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.item_scraped, signal=signals.item_scraped)
        return spider

    def item_scraped(self, item: JobCheck) -> None:
        self._assessed_urls.add(item["url"])
        host = get_site(item["url"])
        self._checks_by_host[host] += 1
        if item["ok"] is None:
            self._inconclusive_by_host[host] += 1

    def closed(self, reason: str) -> None:
        if reason != "finished":
            return  # don't bury the real cause under follow-up errors

        # Every link must get assessed, even if inconclusively, otherwise it's a bug
        for url in sorted(self._expected_urls - self._assessed_urls):
            self.logger.error(f"Link not assessed: {url}")

        # Mostly inconclusive checks of a site mean checking the site doesn't work
        for host, count in sorted(self._checks_by_host.items()):
            inconclusive_count = self._inconclusive_by_host[host]
            if (
                count >= MIN_CHECKS_PER_HOST
                and inconclusive_count / count > MAX_INCONCLUSIVE_RATIO
            ):
                self.logger.error(
                    f"Checks of {host} don't work: {inconclusive_count}/{count} inconclusive"
                )

    async def start(self) -> AsyncGenerator[Request]:
        if not self._start_urls:
            raise ValueError("No links provided")
        self.logger.info(f"Loading {len(self._start_urls)} links")
        startupjobs_urls = []  # StartupJobs URLs bulk
        jobscz_urls = []  # checked only after probing the beta bucket
        profesiask_urls = []  # slow because of the WAF, so scheduled last
        linkedin_urls_count = 0
        for url in self._start_urls:
            if is_linkedin_url(url):
                linkedin_urls_count += 1
                continue
            self._expected_urls.add(url)
            if is_startupjobs_url(url):
                startupjobs_urls.append(url)
            elif is_jobscz_url(url):
                jobscz_urls.append(url)
            elif is_profesiask_url(url):
                profesiask_urls.append(url)
            else:
                yield self._http_request(url, "HEAD")
        if linkedin_urls_count:
            self.logger.info(
                f"Skipping {linkedin_urls_count} LinkedIn links, not supported"
            )
        if startupjobs_urls:
            yield Request(
                STARTUPJOBS_EXPORT_URL,
                callback=self.check_startupjobs,
                errback=self.check_failure,
                cb_kwargs={"urls": startupjobs_urls},
                dont_filter=True,
            )
        if jobscz_urls:
            yield Request(
                BETA_BUCKET_PROBE_URL,
                callback=self.probe_jobscz,
                errback=self.check_failure,
                cb_kwargs={"urls": jobscz_urls},
                dont_filter=True,
                meta={
                    "dont_redirect": True,
                    "dont_merge_cookies": True,
                    "handle_httpstatus_list": [301, 302],
                },
            )
        for url in profesiask_urls:
            # GET, not HEAD, as expired ads respond with 200 and a notice
            yield Request(
                url,
                callback=self.check_profesiask,
                errback=self.check_failure,
                cb_kwargs={"urls": [url]},
                dont_filter=True,
            )

    def _http_request(self, url: str, method: str) -> Request:
        return Request(
            url,
            method=method,
            callback=self.check_http,
            errback=self.check_failure,
            cb_kwargs={"urls": [url]},
            # Otherwise links redirecting to the same page get dropped on Apify
            dont_filter=True,
        )

    def check_http(
        self, response: Response, urls: list[str]
    ) -> Generator[JobCheck | Request]:
        url = urls[0]
        self.logger.info(f"Checking {url} (HTTP {response.request.method})")
        reason = f"HTTP {response.status}"
        if response.status == 200:
            yield JobCheck(url=url, ok=True, reason=reason)
        elif response.status in (404, 410):
            yield JobCheck(url=url, ok=False, reason=reason)
        elif response.status in (405, 501) and response.request.method == "HEAD":
            self.logger.info(f"HEAD not supported by {url}, trying GET")
            yield self._http_request(url, "GET")
        else:
            self.logger.warning(f"Inconclusive check of {url}: {reason}")
            yield JobCheck(url=url, ok=None, reason=reason)

    def probe_jobscz(self, response: Response, urls: list[str]) -> Generator[Request]:
        # Jobs.cz puts visitors to an A/B test bucket at random, and bucket A
        # gets redirected to beta.jobs.cz. The beta site responds with 404 to
        # live jobs of companies with custom career sites, the same 404 as to
        # expired jobs, so there's no way to tell them apart. The cookie jar
        # is shared, so the first bucket assigned would affect all checks.
        cookie = get_classic_site_cookie(response.headers.getlist("Set-Cookie"))
        self.logger.info(f"Using jobs.cz classic site cookie: {cookie['value']}")
        for url in urls:
            # GET, not HEAD, so that the page can be verified
            yield Request(
                url,
                cookies=[cookie],
                callback=self.check_jobscz,
                errback=self.check_failure,
                cb_kwargs={"urls": [url]},
                dont_filter=True,
            )

    def check_jobscz(self, response: Response, urls: list[str]) -> Generator[JobCheck]:
        url = urls[0]
        self.logger.info(f"Checking {url} (jobs.cz, {response.url})")
        reason = f"JOBSCZ HTTP {response.status}"
        if response.status in (404, 410):
            if is_beta_site(response.url):
                self.logger.warning(f"Inconclusive check of {url}: {reason} (beta)")
                yield JobCheck(url=url, ok=None, reason=reason)
            else:
                yield JobCheck(url=url, ok=False, reason=reason)
        elif response.status == 200:
            if site := get_jobscz_site(response):
                yield JobCheck(url=url, ok=True, reason=f"{reason} ({site})")
            else:
                raise UnexpectedPageError(
                    f"Unexpected jobs.cz page: {url} → {response.url}"
                )
        else:
            self.logger.warning(f"Inconclusive check of {url}: {reason}")
            yield JobCheck(url=url, ok=None, reason=reason)

    def check_profesiask(
        self, response: Response, urls: list[str]
    ) -> Generator[JobCheck]:
        url = urls[0]
        self.logger.info(f"Checking {url} (Profesia.sk)")
        try:
            raise_for_waf_challenge(response)
        except WAFChallengeError as e:
            # don't report blocked request as expired job
            self.logger.warning(f"Inconclusive check of {url}: {e}")
            yield JobCheck(url=url, ok=None, reason="PROFESIASK WAF")
        else:
            if response.status not in (200, 404, 410):
                # e.g. '403 Forbidden' through some proxies, which isn't a WAF
                # challenge, but doesn't tell anything about the job either
                reason = f"PROFESIASK HTTP {response.status}"
                self.logger.warning(f"Inconclusive check of {url}: {reason}")
                yield JobCheck(url=url, ok=None, reason=reason)
            elif gone_reason := get_gone_reason(response):
                reason = f"PROFESIASK {gone_reason.upper()}"
                yield JobCheck(url=url, ok=False, reason=reason)
            elif response.css('[itemprop="datePosted"]').get(None):
                yield JobCheck(url=url, ok=True, reason="PROFESIASK")
            else:
                raise UnexpectedPageError(
                    f"Unexpected profesia.sk page: {url} → {response.url}"
                )

    def check_failure(self, failure: Failure) -> Generator[JobCheck]:
        reason = failure.type.__name__
        for url in failure.request.cb_kwargs["urls"]:
            self.logger.warning(f"Inconclusive check of {url}: {reason}")
            yield JobCheck(url=url, ok=None, reason=reason)

    def check_startupjobs(
        self, response: Response, urls: list[str]
    ) -> Generator[JobCheck]:
        self.logger.info(f"Checking {len(urls)} URLs (StartupJobs)")
        if response.status != 200:
            reason = f"STARTUPJOBS HTTP {response.status}"
            for url in urls:
                self.logger.warning(f"Inconclusive check of {url}: {reason}")
                yield JobCheck(url=url, ok=None, reason=reason)
            return
        data = response.json()
        current_ids = set()
        for offer in data.get("offers", []):
            try:
                current_ids.add(parse_startupjobs_id(offer["url"]))
            except ValueError:
                self.logger.warning(f"Skipping feed offer: {offer['url']}")
        for url in urls:
            try:
                startupjobs_id = parse_startupjobs_id(url)
            except ValueError:
                self.logger.warning(f"Inconclusive check of {url}: unknown ID")
                yield JobCheck(url=url, ok=None, reason="STARTUPJOBS UNKNOWN ID")
                continue
            if startupjobs_id in current_ids:
                yield JobCheck(url=url, ok=True, reason="STARTUPJOBS")
            else:
                yield JobCheck(url=url, ok=False, reason="STARTUPJOBS")


def get_site(url: str) -> str:
    # Good enough for .cz and .com, groups e.g. company subdomains of jobs.cz
    return ".".join((urlparse(url).hostname or "").split(".")[-2:])


def is_linkedin_url(url: str) -> bool:
    return "linkedin.com" in urlparse(url).netloc


def is_jobscz_url(url: str) -> bool:
    hostname = urlparse(url).hostname or ""
    return hostname == "jobs.cz" or hostname.endswith(".jobs.cz")


def get_jobscz_site(response: Response) -> str | None:
    hostname = urlparse(response.url).hostname
    if hostname == "beta.jobs.cz":
        if response.css('script[type="application/ld+json"]::text').re(
            r'"@type"\s*:\s*"JobPosting"'
        ):
            return "beta"
    elif hostname == "www.jobs.cz":
        if response.css('[data-jobad="body"]'):
            return "classic"
    elif response.css("script::text").re(r"__LMC_CAREER_WIDGET__") or response.css(
        'script[src*="assets/"][src*=".min.js"]'
    ):
        # Career sites render jobs with JavaScript, so a job widget is all
        # there is to see. Expired jobs are 404, but some sites respond with
        # 200 to any job ID, so only jobs.cz URLs are reliable for those
        return "widget"
    return None


def is_startupjobs_url(url: str) -> bool:
    return "startupjobs.cz" in urlparse(url).netloc


def is_profesiask_url(url: str) -> bool:
    return "profesia.sk" in urlparse(url).netloc


def parse_startupjobs_id(url: str) -> int:
    if match := re.search(r"/nabidka/(\d+)/", url):
        return int(match.group(1))
    raise ValueError(f"Could not parse StartupJobs ID: {url}")
