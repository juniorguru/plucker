from collections.abc import AsyncGenerator, Generator
from enum import StrEnum
from io import BytesIO
from urllib.parse import urljoin

from favicon import Icon, favicon
from PIL import Image
from scrapy import Request, Spider as BaseSpider
from scrapy.http.response import Response

from jg.plucker.items import JobLogo
from jg.plucker.scrapers import parse_links


class Format(StrEnum):
    PNG = "png"
    JPG = "jpg"
    ICO = "ico"
    WEBP = "webp"
    BMP = "bmp"
    GIF = "gif"
    AVIF = "avif"

    @classmethod
    def from_content_type(cls, content_type: str) -> Format:
        if content_type.startswith("image/png"):
            return cls.PNG
        elif content_type.startswith("image/jpeg"):
            return cls.JPG
        elif content_type.startswith("image/x-icon"):
            return cls.ICO
        elif content_type.startswith("image/webp"):
            return cls.WEBP
        elif content_type.startswith("image/bmp"):
            return cls.BMP
        elif content_type.startswith("image/gif"):
            return cls.GIF
        elif content_type.startswith("image/avif"):
            return cls.AVIF
        raise ValueError(f"Unsupported content type: {content_type!r}")


class Spider(BaseSpider):
    name = "job-logos"

    min_items = 1

    def __init__(
        self, name: str | None = None, links: list[dict[str, str]] | None = None
    ):
        super().__init__(name)
        parse_links(links)  # validates, but normalizes URLs, which wouldn't match
        self._start_urls = list(dict.fromkeys(link["url"] for link in links or []))

    async def start(self) -> AsyncGenerator[Request]:
        for url in self._start_urls:
            # The input URL as given, so that it matches on the junior.guru side
            yield Request(
                url,
                callback=self.parse,
                cb_kwargs={"source_url": url},
                dont_filter=True,
            )

    def parse(
        self, response: Response, source_url: str
    ) -> Generator[Request | JobLogo]:
        if not response.request:
            raise ValueError("Response does not have a request")
        request = response.request

        details = []
        if response.url != request.url:
            details.append(f"redirected from {request.url}")
        if source_url != request.url:
            details.append(f"originally {source_url}")
        details = f" ({' '.join(details)})" if details else ""
        self.logger.info(f"Processing {response.url}{details}")

        content_type = (response.headers.get("Content-Type") or b"").decode("utf8")
        if not content_type.startswith(("image/", "text/")):
            self.logger.warning(f"Declared content type: {content_type!r}")
        elif "image/svg" in content_type:
            self.logger.warning("SVG images are not supported")
            return
        else:
            self.logger.debug(f"Declared content type: {content_type!r}")

        try:
            html = response.text
        except AttributeError:
            self.logger.debug("Assuming image URL")
            with Image.open(BytesIO(response.body)) as img:
                content_type = img.get_format_mimetype() or content_type
                self.logger.debug(f"Detected content type: {content_type!r}")
                width, height = img.size
                self.logger.debug(f"Image size: {width}x{height}")
            yield JobLogo(
                image_url=response.body,
                original_image_url=response.url,
                width=width,
                height=height,
                format=Format.from_content_type(content_type),
                source_url=source_url,
            )
        else:
            self.logger.debug("Assuming company homepage URL")
            favicon_url = urljoin(response.url, "/favicon.ico")
            self.logger.debug(f"Favicon URL: {favicon_url}")
            if response.url == favicon_url:
                self.logger.warning("Favicon URL doesn't return an image")
                return
            yield Request(
                favicon_url,
                callback=self.parse,
                cb_kwargs={"source_url": source_url},
            )
            icons: set[Icon] = {
                icon
                for icon in favicon.tags(response.url, html)
                if icon.url != favicon_url
            }
            self.logger.debug(f"Found {len(icons)} other URLs in HTML tags")
            for icon in icons:
                if icon.url.startswith("data:"):
                    self.logger.warning(f"Skipping data URL favicon at {response.url}")
                    continue
                yield Request(
                    icon.url,
                    callback=self.parse,
                    cb_kwargs={"source_url": source_url},
                )
