import re

from aiohttp.client import ClientSession
from bs4 import BeautifulSoup


class MediafireExtractor(object):
    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def check(url: str) -> bool:
        return bool(re.match(r"^https?:\/\/(www\.)?mediafire\.com", url))

    @staticmethod
    async def get_url(session: ClientSession, url: str) -> str:
        async with session.get(url) as response:
            page = BeautifulSoup(await response.text(), "lxml")
            info = page.find("a", {"aria-label": "Download file"})

            return info["href"]
