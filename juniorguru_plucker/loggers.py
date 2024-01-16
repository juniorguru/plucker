import logging
from functools import wraps
from typing import Callable

from apify.log import ActorLogFormatter
from scrapy.settings import Settings
from scrapy.utils import log as scrapy_logging


def configure_apify_logging(logging_level: str) -> Callable:
    handler = logging.StreamHandler()
    handler.setFormatter(ActorLogFormatter(include_logger_name=True))

    apify_logger = logging.getLogger("apify")
    apify_logger.setLevel(logging_level)
    apify_logger.addHandler(handler)

    apify_client_logger = logging.getLogger("apify_client")
    apify_client_logger.setLevel(logging_level)
    apify_client_logger.addHandler(handler)

    def decorator(configure_logging: Callable) -> Callable:
        @wraps(configure_logging)
        def wrapper(*args, **kwargs):
            configure_logging(*args, **kwargs)

            # We modify the root logger to ensure proper display of logs from spiders when using the `self.logger`
            # property within spiders. See details in the Spider logger property:
            # https://github.com/scrapy/scrapy/blob/2.11.0/scrapy/spiders/__init__.py#L43:L46.
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)
            root_logger.setLevel(logging_level)

            # We modify other loggers only by setting up their log level. A custom log handler is added
            # only to the root logger to avoid duplicate log messages.
            scrapy_logger = logging.getLogger("scrapy")
            scrapy_logger.setLevel(logging_level)

            twisted_logger = logging.getLogger("twisted")
            twisted_logger.setLevel(logging_level)

            filelock_logger = logging.getLogger("filelock")
            filelock_logger.setLevel(logging_level)

            hpack_logger = logging.getLogger("hpack")
            hpack_logger.setLevel(logging_level)

            # Set the HTTPX logger explicitly to the WARNING level, because it is too verbose and spams the logs with useless
            # messages, especially when running on the platform
            httpx_logger = logging.getLogger("httpx")
            httpx_logger.setLevel(logging.WARNING)

        return wrapper

    return decorator


def get_logging_level(settings: Settings, argv: list[str]) -> str:
    if "--debug" in argv or "-d" in argv:
        return "DEBUG"
    return settings.get("LOG_LEVEL", "INFO")


def configure_logging(settings: Settings, argv: list[str]):
    logging_level = get_logging_level(settings, argv)
    scrapy_logging.configure_logging = configure_apify_logging(logging_level)(
        scrapy_logging.configure_logging
    )
