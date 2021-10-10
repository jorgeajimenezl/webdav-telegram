import re
import aiohttp

from bs4 import BeautifulSoup
from aiohttp.client import ClientSession
from services.extractors.extractor import Extractor


class ZippyshareExtractor(Extractor):
    def __init__(self) -> None:
        super().__init__()

    @staticmethod
    def check(url: str) -> bool:
        return bool(re.match(r"^https?:\/\/([\w\d]+)\.zippyshare", url))

    @staticmethod
    async def get_url(session: ClientSession, url: str) -> str:
        # Taked from github random code

        r = re.match(r"https?:\/\/([\w\d]+)\.zippyshare", url)
        www = r.group(1)

        async with session.get(url) as response:
            page = BeautifulSoup(await response.text(), "lxml")
            try:
                js_script = page.find("div", {"class": "center"}).find_all("script")[1]
            except IndexError:
                js_script = page.find("div", {"class": "right"}).find_all("script")[0]

            for tag in js_script:
                if not "document.getElementById('dlbutton')" in tag:
                    continue

                url_raw = re.search(
                    r"= (?P<url>\".+\" \+ " r"(?P<math>\(.+\)) .+);", tag
                )
                math = re.search(r"= (?P<url>\".+\" \+ " r"(?P<math>\(.+\)) .+);", tag)
                if not url_raw or not math:
                    continue

                url_raw, math = url_raw.group("url"), math.group("math")
                numbers = []
                expression = []

                for e in math.strip("()").split():
                    try:
                        numbers.append(int(e))
                    except ValueError:
                        expression.append(e)

                try:
                    result = None
                    if expression[0] == "%" and expression[2] == "%":
                        first_result = numbers[0] % numbers[1]
                        second_result = numbers[2] % numbers[3]
                        if expression[1] == "+":
                            result = str(first_result + second_result)
                        elif expression[1] == "-":
                            result = str(first_result - second_result)
                        else:
                            raise ValueError("Unexpected value to calculate")
                    else:
                        raise ValueError("Unexpected results of expression")
                except IndexError:
                    raise ValueError("Unexpected results of array")
                else:
                    url_raw = url_raw.replace(math, result)
                    link = f"https://{www}.zippyshare.com"

                if result is None:
                    raise ValueError("Unexpected response, result is empty")

                for i in url_raw.split("+"):
                    link += i.strip().strip('"')

                return link
