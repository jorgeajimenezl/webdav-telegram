import re
import aiohttp

from bs4 import BeautifulSoup
from aiohttp.client import ClientSession
from services.extractors.extractor import Extractor
from services.extractors.zippyshare import ZippyshareExtractor


class AnimeFLVExtractor(Extractor):
    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def check(url: str) -> bool:
        return bool(re.match(r"^https?://(www\.)?animeflv\.net", url))

    @staticmethod
    async def get_url(session: ClientSession, url: str) -> str:
        async with session.get(url) as response:
            page = BeautifulSoup(await response.text(), "lxml")
            pass