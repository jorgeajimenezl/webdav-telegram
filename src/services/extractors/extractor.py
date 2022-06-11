from typing import Dict, List, Optional

from aiohttp.client import ClientSession


class Extractor(object):
    def __init__(self) -> None:
        raise Exception("Isn't necessary instantiate this object")

    @staticmethod
    def check(url: str) -> bool:
        raise NotImplementedError

    async def get_options(session: ClientSession, url: str) -> List[Dict[str, str]]:
        return None

    @staticmethod
    async def execute(session: ClientSession, url: str, **kwargs) -> None:
        raise NotImplementedError

    @staticmethod
    async def get_url(session: ClientSession, url: str) -> str:
        raise NotImplementedError
