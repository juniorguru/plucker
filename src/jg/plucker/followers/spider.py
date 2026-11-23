import json
import re
from collections.abc import AsyncGenerator, Callable, Generator
from datetime import date
from urllib.parse import urlparse

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response

from jg.plucker.items import Followers


FB_DESCRIPTION_RE = re.compile(
    r"""
        ([\d.,\s]+)  # group 1: number with optional commas and spaces
        \s+          # one or more whitespace
        (?:          # non-capturing group for count label variants
            likes?                 # English: like or likes
            | followers            # English: followers
            | sledující            # Czech: sledující/sledujících (followers)
            | to\s+se\s+mi\s+líbí  # Czech: to se mi líbí (likes)
        )
    """,
    re.IGNORECASE | re.VERBOSE,
)

IG_DESCRIPTION_RES = [
    re.compile(r"^(\d+) Followers, "),  # English
    re.compile(r"^Počet sledujících: (\d+), "),  # Czech
]

LOGIN_PATHS = ("/login", "/accounts/login")

# Meta's own link preview crawler gets the og:description on Instagram profiles
LINK_PREVIEW_USER_AGENT = (
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
)

MAX_ATTEMPTS = 2


class Spider(BaseSpider):
    name = "followers"

    min_items = 0

    custom_settings = {
        "USER_AGENT": "",
        "DOWNLOAD_HANDLERS": {
            "http": "scrapy_impersonate.ImpersonateDownloadHandler",
            "https": "scrapy_impersonate.ImpersonateDownloadHandler",
        },
        "DOWNLOADER_MIDDLEWARES": {
            "scrapy_impersonate.RandomBrowserMiddleware": 1000,
        },
    }

    def __init__(self, name: str | None = None, today: date | str | None = None):
        super().__init__(name)
        if isinstance(today, str):
            today = date.fromisoformat(today)
        self.today = today or date.today()

    async def start(self) -> AsyncGenerator[Request]:
        yield Request(
            "https://mastodonczech.cz/@honzajavorek",
            self.parse_mastodon,
        )
        yield self.profile_request(
            "https://www.facebook.com/juniordotguru",
            self.parse_facebook,
            name="facebook",
        )
        yield self.profile_request(
            "https://www.facebook.com/honzajavorek/?__xts__=1",
            self.parse_facebook,
            name="facebook_personal",
        )
        yield self.profile_request(
            "https://www.instagram.com/juniordotguru/",
            self.parse_instagram,
            name="instagram",
            headers={"User-Agent": LINK_PREVIEW_USER_AGENT},
        )
        yield self.profile_request(
            "https://www.instagram.com/honza.javorek/",
            self.parse_instagram,
            name="instagram_personal",
            headers={"User-Agent": LINK_PREVIEW_USER_AGENT},
        )
        yield Request(
            (
                "https://www.linkedin.com/posts/"
                "honzajavorek_p%C5%AFl-rok-samostudia-programov%C3%A1n%C3%AD-a-%C4%8Dlov%C4%9Bk-activity-7300443605666545664-S7yp"
                "?rcm=ACoAAACB93ABHHj4UI2winetGMZHboHlZIZojJA"
            ),
            self.parse_linkedin,
            cb_kwargs={"name": "linkedin_personal"},
        )
        yield Request(
            (
                "https://www.linkedin.com/posts/"
                "juniorguru_sledujte-honza-javorek-na-jeho-osobn%C3%ADm-profilu-activity-7307699650512191489-IvLD"
                "?utm_source=share&utm_medium=member_desktop&rcm=ACoAAACB93ABHHj4UI2winetGMZHboHlZIZojJA"
            ),
            self.parse_linkedin,
            cb_kwargs={"name": "linkedin"},
        )

    def parse_mastodon(self, response: Response) -> Followers:
        self.logger.info(f"Parsing mastodon from {get_domain(response.url)}")
        selector = response.css('meta[name="description"]::attr(content)')
        if match := selector.re(r"(?i)([\d,]+)\s+(followers|sledujících)"):
            return Followers(
                date=self.today,
                name="mastodon",
                count=int(match[0].replace(",", "")),
            )
        raise ValueError("Could not find followers count")

    def parse_linkedin(self, response: Response, name: str) -> Followers:
        self.logger.info(f"Parsing {name} from {get_domain(response.url)}")
        if ld_json := response.css('script[type="application/ld+json"]::text').get():
            self.logger.info("Found ld+json")
            data = json.loads(ld_json)
            self.logger.info("Parsed ld+json")
            count = data["author"]["interactionStatistic"]["userInteractionCount"]
            self.logger.info(f"Followers count: {count}")
            if count:
                return Followers(date=self.today, name=name, count=count)
        self.logger.info("Parsing cards")
        texts = response.css(
            ".public-post-author-card__followers::text, .base-main-feed-card__entity-lockup p::text"
        ).getall()
        for text in texts:
            self.logger.info(f"Parsing text: {text!r}")
            try:
                count = int(re.sub(r"\D", "", text))
                return Followers(date=self.today, name=name, count=count)
            except ValueError:
                self.logger.debug(f"Could not parse text: {text!r}")
        raise ValueError("Could not find followers count:\n\n" + response.text)

    def profile_request(
        self,
        url: str,
        callback: Callable,
        name: str,
        headers: dict[str, str] | None = None,
    ) -> Request:
        return Request(
            url,
            callback,
            cb_kwargs={"name": name, "attempt": 1},
            headers=headers,
            meta={"handle_httpstatus_list": [404]},
        )

    def parse_facebook(
        self, response: Response, name: str, attempt: int = 1
    ) -> Generator[Followers | Request]:
        yield from self.parse_profile(
            response, name, attempt, parse_facebook_description
        )

    def parse_instagram(
        self, response: Response, name: str, attempt: int = 1
    ) -> Generator[Followers | Request]:
        yield from self.parse_profile(
            response, name, attempt, parse_instagram_description
        )

    def parse_profile(
        self,
        response: Response,
        name: str,
        attempt: int,
        parse_description: Callable[[str], int],
    ) -> Generator[Followers | Request]:
        self.logger.info(f"Parsing {name} from {get_domain(response.url)}")
        redirect_urls = response.meta.get("redirect_urls", [])
        if is_login_redirect([*redirect_urls, response.url]):
            if attempt < MAX_ATTEMPTS:
                self.logger.warning(f"Redirected to login, retrying {name}")
                if response.request is None:
                    raise ValueError(f"Missing request to retry: {name}")
                yield response.request.replace(
                    url=redirect_urls[0] if redirect_urls else response.url,
                    cb_kwargs={"name": name, "attempt": attempt + 1},
                    meta={"handle_httpstatus_list": [404], "dont_cache": True},
                    dont_filter=True,
                )
            else:
                self.logger.error(
                    f"Redirected to login {attempt} times, skipping {name}"
                )
            return
        if response.status != 200:
            raise ValueError(f"Unexpected HTTP status {response.status}: {name}")
        selector = 'meta[property="og:description"]::attr(content)'
        if description := response.css(selector).get():
            count = parse_description(description)
            yield Followers(date=self.today, name=name, count=count)
        else:
            raise ValueError("Could not find og:description:\n\n" + response.text)


def parse_facebook_description(description: str) -> int:
    """Parse followers count from Facebook's og:description"""
    if match := FB_DESCRIPTION_RE.search(description):
        return int(re.sub(r"\D", "", match.group(1)))
    raise ValueError(f"Could not parse followers: {description!r}")


def parse_instagram_description(description: str) -> int:
    """Parse followers count from Instagram's og:description"""
    for description_re in IG_DESCRIPTION_RES:
        if match := description_re.search(description):
            return int(match.group(1))
    raise ValueError(f"Could not parse followers: {description!r}")


def is_login_redirect(urls: list[str]) -> bool:
    """Tell whether any of the URLs is a login page"""
    return any(urlparse(url).path.startswith(LOGIN_PATHS) for url in urls)


def get_domain(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    hostname = hostname.removeprefix("www.")
    parts = hostname.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname
