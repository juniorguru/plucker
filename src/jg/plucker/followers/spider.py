import json
import re
from datetime import date
from typing import AsyncGenerator

from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response

from jg.plucker.items import Followers


class Spider(BaseSpider):
    name = "followers"

    min_items = 0

    async def start(self) -> AsyncGenerator[Request, None]:
        today = date.today()
        yield Request(
            "https://mastodonczech.cz/@honzajavorek",
            self.parse_mastodon,
            cb_kwargs={"today": today},
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
            cb_kwargs={"today": today},
        )

    def parse_mastodon(self, response: Response, today: date) -> Followers:
        self.logger.info("Parsing Mastodon")
        selector = response.css('meta[name="description"]::attr(content)')
        if match := selector.re(r"(?i)([\d,]+)\s+(followers|sledujících)"):
            return Followers(
                date=today,
                name="mastodon",
                count=int(match[0].replace(",", "")),
            )
        raise ValueError("Could not find followers count")

    def parse_linkedin(
        self, response: Response, today: date, name: str = "linkedin"
    ) -> Followers:
        self.logger.info(f"Parsing Linkedin ({name})")
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
