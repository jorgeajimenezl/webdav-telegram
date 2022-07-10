import aiohttp
import os
import re
from typing import List

from aiodav.client import Client as DavClient
from async_executor.task import TaskState
from modules.service import Service
from pyrogram import emoji
from pyrogram.types import Message
from urllib.parse import urlparse

from services.extractors.animeflv import AnimeFLVExtractor
from services.extractors.extractor import Extractor
from services.extractors.mediafire import MediafireExtractor
from services.extractors.zippyshare import ZippyshareExtractor


class HttpService(Service):
    """
    Download web file and upload to webdav
    """

    EXTRACTORS: List[Extractor] = [
        AnimeFLVExtractor,
        # ZippyshareExtractor,
        MediafireExtractor,
    ]

    def __init__(self, id: int, *args, **kwargs) -> None:
        super().__init__(id, *args, **kwargs)

    @staticmethod
    def check(m: Message) -> bool:
        return bool(m.text) and bool(
            re.fullmatch(
                r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=\[\]]*)",
                m.text,
            )
        )

    async def start(self) -> None:
        self._set_state(TaskState.STARTING)

        async with DavClient(
            hostname=self.webdav_hostname,
            login=self.webdav_username,
            password=self.webdav_password,
            timeout=self.timeout,
            chunk_size=2097152,
        ) as dav:
            async with aiohttp.ClientSession() as session:
                url = self.kwargs.get("url", self.file_message.text)

                for e in HttpService.EXTRACTORS:
                    if e.check(url):
                        url = await e.get_url(session, url)

                        # Try to execute extractor own method,
                        # else invoke default http downloader
                        try:
                            await e.execute(session, url, **self.kwargs)
                            return
                        except NotImplementedError:
                            pass
                        except Exception as e:
                            raise e

                        break

                async with session.get(url) as response:
                    try:
                        d = response.headers["content-disposition"]
                        filename = re.findall("filename=(.+)", d)[0]
                    except Exception:
                        req = urlparse(url)
                        filename = os.path.basename(req.path)

                    gen = response.content.iter_chunked(2097152)
                    await self.upload(
                        dav,
                        filename,
                        response.content_length,
                        gen,
                    )

        return None
