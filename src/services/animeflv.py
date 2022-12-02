import re
import os
import aiofiles
import tempfile

from animeflv import AnimeFLV
from aiodav.client import Client as DavClient
from pyrogram import emoji
from async_executor.task import TaskState
from modules.service import Service
from pyrogram.types import Message
from services.http import HttpService
from urllib.parse import urlparse
from utils import wrap_request_non_empty as w


class AnimeFLVService(Service):
    """
    Download AnimeFLV file and upload to webdav
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    @staticmethod
    def check(m: Message):
        return bool(m.text) and bool(
            re.match(r"^https?:\/\/(www[0-9]*\.)?animeflv\.net", m.text)
        )

    async def start(self) -> None:
        self.set_state(TaskState.STARTING)
        url = urlparse(self.kwargs.get("url", self.file_message.text)).path

        async with DavClient(
            hostname=self.webdav_hostname,
            login=self.webdav_username,
            password=self.webdav_password,
            timeout=self.timeout,
            chunk_size=2097152,
        ) as dav:
            with AnimeFLV() as api:
                fmt, desc = url.split("/")

                # Episode
                if fmt == "ver":
                    anime, _, id = desc.rpartition("-")
                    link = w(api.get_links, anime, id)

                    for x in link:
                        if x.server.lower() == "mega":
                            child = HttpService(url=x.url, **self.kwargs)
                            self.schedule_child(child)

                # Anime
                if fmt == "anime":
                    info = w(api.get_anime_info, desc)

                    for episode in info.episodes:
                        for link in w(api.get_links, episode.anime, episode.id):
                            if link.server.lower() == "mega":
                                child = HttpService(url=x.url, **self.kwargs)
                                self.schedule_child(child)

            await self.wait_for_childs()
            return None
