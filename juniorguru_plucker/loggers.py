import logging
from functools import wraps
from typing import Callable

from apify.log import ActorLogFormatter
from scrapy.settings import Settings
from scrapy.utils import log as scrapy_logging


CUSTOM_LOGGER_NAMES = ["juniorguru_plucker", "apify", "apify_client"]

SCRAPY_LOGGER_NAMES = ["filelock", "hpack", "httpx", "scrapy", "twisted"]

ALL_LOGGER_NAMES = CUSTOM_LOGGER_NAMES + SCRAPY_LOGGER_NAMES


def configure_logging(settings: Settings, argv: list[str]):
    logging_level = get_logging_level(settings, argv)

    handler = logging.StreamHandler()
    handler.setFormatter(ActorLogFormatter(include_logger_name=True))

    # Local loggers have to be set up here and in the `reconfigure_scrapy_logging` as well to be able
    # to use them both from CLI and Scrapy components.
    for logger_name in CUSTOM_LOGGER_NAMES:
        configure_logger(logger_name, logging_level, handler)

    # We can't attach our log handler to the loggers normally, because Scrapy would remove them in the `configure_logging`
    # call here: https://github.com/scrapy/scrapy/blob/2.11.0/scrapy/utils/log.py#L113 (even though
    # `disable_existing_loggers` is set to False :facepalm:). We need to monkeypatch Scrapy's `configure_logging` method
    # like this, so that our handler is attached right after Scrapy calls the `configure_logging` method, because
    # otherwise we would lose some log messages.
    scrapy_logging.configure_logging = reconfigure_scrapy_logging(
        logging_level, handler
    )(scrapy_logging.configure_logging)


def reconfigure_scrapy_logging(
    logging_level: str, *handlers: logging.StreamHandler
) -> Callable:
    def decorator(configure_logging: Callable) -> Callable:
        @wraps(configure_logging)
        def wrapper(*args, **kwargs):
            # We need to manually configure both the root logger and all Scrapy-associated loggers. Configuring only the root
            # logger is not sufficient, as Scrapy will override it with its own settings. Scrapy uses these four primary
            # loggers - https://github.com/scrapy/scrapy/blob/2.11.0/scrapy/utils/log.py#L60:L77
            configure_logging(*args, **kwargs)

            # We modify the root (None) logger to ensure proper display of logs from spiders when using the `self.logger`
            # property within spiders. See details in the Spider logger property:
            # https://github.com/scrapy/scrapy/blob/2.11.0/scrapy/spiders/__init__.py#L43:L46.
            configure_logger(None, logging_level, *handlers)

            # We modify other loggers only by setting up their log level. A custom log handler is added
            # only to the root logger to avoid duplicate log messages.
            for logger_name in ALL_LOGGER_NAMES:
                configure_logger(logger_name, logging_level)

            # Set the HTTPX logger explicitly to the WARNING level, because it is too verbose and spams the logs with useless
            # messages, especially when running on the platform.
            configure_logger("httpx", "WARNING")

        return wrapper

    return decorator


def configure_logger(
    logger_name: str | None, log_level: str, *handlers: logging.StreamHandler
) -> None:
    logger = logging.getLogger(logger_name)
    logger.setLevel(log_level)
    logger.handlers = []
    for handler in handlers:
        logger.addHandler(handler)


def get_logging_level(settings: Settings, argv: list[str]) -> str:
    if "--debug" in argv or "-d" in argv:
        return "DEBUG"
    return settings.get("LOG_LEVEL")
