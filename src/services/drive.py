import re
from async_executor.task import TaskState
from modules.service import Service
from pyrogram.types import Message
from aiodav.client import Client as DavClient


class DriveService(Service):
    def __init__(self, id: int, *args, **kwargs) -> None:
        super().__init__(id, *args, **kwargs)

    @staticmethod
    def check(m: Message):
        return bool(m.text) and bool(
            re.match(r"^https?:\/\/(www\.)?drive\.google\.com", m.text)
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
            pass
