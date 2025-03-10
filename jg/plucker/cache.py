import gzip
import io
import logging
import pickle
import struct
from time import time

from apify import Configuration
from apify.apify_storage_client import ApifyStorageClient
from apify.scrapy._async_thread import AsyncThread
from apify.storages import KeyValueStore
from scrapy import Request, Spider
from scrapy.http.headers import Headers
from scrapy.http.response import Response
from scrapy.responsetypes import responsetypes
from scrapy.settings import BaseSettings
from scrapy.utils.request import RequestFingerprinterProtocol


logger = logging.getLogger("jg.plucker.cache")


class CacheStorage:
    def __init__(self, settings: BaseSettings):
        self.expiration_max_items = 100
        self.expiration_secs: int = settings.getint("HTTPCACHE_EXPIRATION_SECS")
        self.spider: Spider | None = None
        self._kv: KeyValueStore | None = None
        self._fingerprinter: RequestFingerprinterProtocol | None = None
        self._async_thread: AsyncThread | None = None

    def open_spider(self, spider: Spider) -> None:
        logger.debug("Using Apify key value cache storage", extra={"spider": spider})
        self.spider = spider
        self._fingerprinter = spider.crawler.request_fingerprinter
        kv_name = f"httpcache-{spider.name}"

        async def open_kv() -> KeyValueStore:
            config = Configuration.get_global_configuration()
            if config.is_at_home:
                storage_client = ApifyStorageClient.from_config(config)
                return await KeyValueStore.open(
                    name=kv_name, storage_client=storage_client
                )
            return await KeyValueStore.open(name=kv_name)

        logger.debug("Starting background thread for cache storage's event loop")
        self._async_thread = AsyncThread()
        logger.debug(f"Opening cache storage's {kv_name!r} key value store")
        self._kv = self._async_thread.run_coro(open_kv())

    def close_spider(self, spider: Spider, current_time: int | None = None) -> None:
        assert self._async_thread is not None, "Async thread not initialized"

        logger.info(f"Cleaning up cache items (max {self.expiration_max_items})")
        if 0 < self.expiration_secs:
            if current_time is None:
                current_time = int(time())

            async def expire_kv() -> None:
                assert self._kv is not None, "Key value store not initialized"
                i = 0
                async for item in self._kv.iterate_keys():
                    value = await self._kv.get_value(item.key)
                    try:
                        gzip_time = read_gzip_time(value)
                    except Exception as e:
                        logger.warning(f"Malformed cache item {item.key}: {e}")
                        await self._kv.set_value(item.key, None)
                    else:
                        if self.expiration_secs < current_time - gzip_time:
                            logger.debug(f"Expired cache item {item.key}")
                            await self._kv.set_value(item.key, None)
                        else:
                            logger.debug(f"Valid cache item {item.key}")
                    if i == self.expiration_max_items:
                        break
                    i += 1

            self._async_thread.run_coro(expire_kv())

        logger.debug("Closing cache storage")
        try:
            self._async_thread.close()
        except KeyboardInterrupt:
            logger.warning("Shutdown interrupted by KeyboardInterrupt!")
        except Exception:
            logger.exception("Exception occurred while shutting down cache storage")
        finally:
            logger.debug("Cache storage closed")

    def retrieve_response(
        self, spider: Spider, request: Request, current_time: int | None = None
    ) -> Response | None:
        assert self._async_thread is not None, "Async thread not initialized"
        assert self._kv is not None, "Key value store not initialized"
        assert self._fingerprinter is not None, "Request fingerprinter not initialized"

        key = self._fingerprinter.fingerprint(request).hex()
        value = self._async_thread.run_coro(self._kv.get_value(key))

        if value is None:
            logger.debug("Cache miss", extra={"request": request})
            return None

        if current_time is None:
            current_time = int(time())
        if 0 < self.expiration_secs < current_time - read_gzip_time(value):
            logger.debug("Cache expired", extra={"request": request})
            return None

        data = from_gzip(value)
        url = data["url"]
        status = data["status"]
        headers = Headers(data["headers"])
        body = data["body"]
        respcls = responsetypes.from_args(headers=headers, url=url, body=body)

        logger.debug("Cache hit", extra={"request": request})
        return respcls(url=url, headers=headers, status=status, body=body)

    def store_response(
        self, spider: Spider, request: Request, response: Response
    ) -> None:
        assert self._async_thread is not None, "Async thread not initialized"
        assert self._kv is not None, "Key value store not initialized"
        assert self._fingerprinter is not None, "Request fingerprinter not initialized"

        key = self._fingerprinter.fingerprint(request).hex()
        data = {
            "status": response.status,
            "url": response.url,
            "headers": dict(response.headers),
            "body": response.body,
        }
        value = to_gzip(data)
        self._async_thread.run_coro(self._kv.set_value(key, value))


def to_gzip(data: dict, mtime: int | None = None) -> bytes:
    with io.BytesIO() as byte_stream:
        with gzip.GzipFile(fileobj=byte_stream, mode="wb", mtime=mtime) as gzip_file:
            pickle.dump(data, gzip_file, protocol=4)
        return byte_stream.getvalue()


def from_gzip(gzip_bytes: bytes) -> dict:
    with io.BytesIO(gzip_bytes) as byte_stream:
        with gzip.GzipFile(fileobj=byte_stream, mode="rb") as gzip_file:
            return pickle.load(gzip_file)


def read_gzip_time(gzip_bytes: bytes) -> int:
    header = gzip_bytes[:10]
    header_components = struct.unpack("<HBBI2B", header)
    return header_components[3]
