from typing import Optional

from aiohttp.client import ClientSession


class Extractor(object):
    def __init__(self) -> None:
        raise Exception("Isn't necessary instantiate this object")

    @staticmethod
    def check(url: str) -> bool:
        raise NotImplementedError

    @staticmethod
    async def get_url(session: ClientSession, url: str) -> str:
        raise NotImplementedError
