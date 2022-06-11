import re
import aiohttp
import cloudscraper

from bs4 import BeautifulSoup
from aiohttp.client import ClientSession
from bs4.element import NavigableString, Tag
from services.extractors.extractor import Extractor
from services.extractors.zippyshare import ZippyshareExtractor
from urllib.parse import unquote

from services.mega import MegaService


class AnimeFLVExtractor(Extractor):
    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def check(url: str) -> bool:
        return bool(re.match(r"^https?:\/\/(www[0-9]*\.)?animeflv\.net", url))

    @staticmethod
    def parse_table(table: Tag):
        columns = [x.string for x in table.thead.tr.find_all("th")]
        rows = []

        for row in table.tbody.find_all("tr"):
            values = row.find_all("td")
            if len(values) != len(columns):
                raise Exception(
                    "Parse Error: don't match values size with columns size"
                )
            rows.append({h: x for h, x in zip(columns, values)})

        return rows

    @staticmethod
    async def execute(_, url: str, **kwargs) -> None:
        # If match with mega url, then, drop this http service and use mega instead
        if bool(re.match(r"^https?:\/\/(www\.)?mega\.nz", url)):
            func = kwargs.get("push_task_method")
            app = kwargs.get("pyrogram")
            user = kwargs.get("user")
            message = kwargs.get("file_message")
            await func(app, user, MegaService, message, url=url)
            return
        raise NotImplementedError

    @staticmethod
    async def get_url(session: ClientSession, url: str) -> str:
        if not re.fullmatch(
            r"^https?:\/\/(www[0-9]*\.)?animeflv\.net\/ver\/[A-Za-z0-9\-]+", url
        ):
            raise Exception("Only episodes download available (send a episode url)")

        scrapper = cloudscraper.create_scraper()
        response = scrapper.get(url)

        page = BeautifulSoup(response.text, "lxml")
        table = page.find("table", attrs={"class": "RTbl"})
        if table is None:
            raise Exception("Unable to get video servers information")

        data = AnimeFLVExtractor.parse_table(table)
        # data.sort(key=(lambda x: x['FORMATO'].string.lower()))

        for d in data:
            if d["FORMATO"].string.lower() == "sub":
                href = unquote(d["DESCARGAR"].a["href"])
                link = re.sub(
                    r"^http[s]?:\/\/ouo.io/[A-Za-z0-9]+\/[A-Za-z0-9]+\?[A-Za-z0-9]+=",
                    "",
                    href,
                )
                match d["SERVIDOR"].string.lower():
                    # case "zippyshare":
                    #     return await ZippyshareExtractor.get_url(session, link)
                    case "mega":
                        return link
                    case _:
                        raise Exception("Unknown download server available")

        raise Exception("Unable to get download stream")
