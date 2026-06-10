import json
import re
from datetime import date
from typing import AsyncGenerator
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
            | sledujících          # Czech: sledujících (followers)
            | to\s+se\s+mi\s+líbí  # Czech: to se mi líbí (likes)
        )
    """,
    re.IGNORECASE | re.VERBOSE,
)

INSTAGRAM_APP_ID = "936619743392459"


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

    async def start(self) -> AsyncGenerator[Request, None]:
        today = date.today()
        yield Request(
            "https://mastodonczech.cz/@honzajavorek",
            self.parse_mastodon,
            cb_kwargs={"today": today},
        )
        yield Request(
            "https://www.facebook.com/juniordotguru",
            self.parse_facebook,
            cb_kwargs={"today": today, "name": "facebook"},
        )
        yield Request(
            "https://www.facebook.com/honzajavorek/?__xts__=1",
            self.parse_facebook,
            cb_kwargs={"today": today, "name": "facebook_personal"},
        )
        yield Request(
            "https://i.instagram.com/api/v1/users/web_profile_info/?username=juniordotguru",
            self.parse_instagram,
            cb_kwargs={"today": today, "name": "instagram"},
            headers={"x-ig-app-id": INSTAGRAM_APP_ID},
        )
        yield Request(
            "https://i.instagram.com/api/v1/users/web_profile_info/?username=honza.javorek",
            self.parse_instagram,
            cb_kwargs={"today": today, "name": "instagram_personal"},
            headers={"x-ig-app-id": INSTAGRAM_APP_ID},
        )
        yield Request(
            (
                "https://www.linkedin.com/posts/"
                "honzajavorek_p%C5%AFl-rok-samostudia-programov%C3%A1n%C3%AD-a-%C4%8Dlov%C4%9Bk-activity-7300443605666545664-S7yp"
                "?rcm=ACoAAACB93ABHHj4UI2winetGMZHboHlZIZojJA"
            ),
            self.parse_linkedin,
            cb_kwargs={"today": today, "name": "linkedin_personal"},
        )
        yield Request(
            (
                "https://www.linkedin.com/posts/"
                "juniorguru_sledujte-honza-javorek-na-jeho-osobn%C3%ADm-profilu-activity-7307699650512191489-IvLD"
                "?utm_source=share&utm_medium=member_desktop&rcm=ACoAAACB93ABHHj4UI2winetGMZHboHlZIZojJA"
            ),
            self.parse_linkedin,
            cb_kwargs={"today": today, "name": "linkedin"},
        )

    def parse_mastodon(self, response: Response, today: date) -> Followers:
        self.logger.info(f"Parsing mastodon from {get_domain(response.url)}")
        selector = response.css('meta[name="description"]::attr(content)')
        if match := selector.re(r"(?i)([\d,]+)\s+(followers|sledujících)"):
            return Followers(
                date=today,
                name="mastodon",
                count=int(match[0].replace(",", "")),
            )
        raise ValueError("Could not find followers count")

    def parse_linkedin(self, response: Response, today: date, name: str) -> Followers:
        self.logger.info(f"Parsing {name} from {get_domain(response.url)}")
        if ld_json := response.css('script[type="application/ld+json"]::text').get():
            self.logger.info("Found ld+json")
            data = json.loads(ld_json)
            self.logger.info("Parsed ld+json")
            count = data["author"]["interactionStatistic"]["userInteractionCount"]
            self.logger.info(f"Followers count: {count}")
            if count:
                return Followers(date=today, name=name, count=count)
        self.logger.info("Parsing cards")
        texts = response.css(
            ".public-post-author-card__followers::text, .base-main-feed-card__entity-lockup p::text"
        ).getall()
        for text in texts:
            self.logger.info(f"Parsing text: {text!r}")
            try:
                count = int(re.sub(r"\D", "", text))
                return Followers(date=today, name=name, count=count)
            except ValueError:
                self.logger.debug(f"Could not parse text: {text!r}")
        raise ValueError("Could not find followers count:\n\n" + response.text)

    def parse_facebook(self, response: Response, today: date, name: str) -> Followers:
        self.logger.info(f"Parsing {name} from {get_domain(response.url)}")
        selector = 'meta[property="og:description"]::attr(content)'
        if description := response.css(selector).get():
            self.logger.info("Found og:description")
            if match := FB_DESCRIPTION_RE.search(description):
                count = int(re.sub(r"\D", "", match.group(1)))
                return Followers(date=today, name=name, count=count)
            self.logger.error(f"Could not parse followers: {description!r}")
        raise ValueError("Could not find followers count:\n\n" + response.text)

    def parse_instagram(self, response: Response, today: date, name: str) -> Followers:
        self.logger.info(f"Parsing {name} from {get_domain(response.url)}")
        try:
            data = json.loads(response.text)
            count = data["data"]["user"]["edge_followed_by"]["count"]
        except (KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                "Could not find followers count in Instagram API response:\n\n"
                + response.text
            ) from exc
        return Followers(date=today, name=name, count=int(count))


def get_domain(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    if hostname.startswith("www."):
        hostname = hostname[4:]
    parts = hostname.split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return hostname
