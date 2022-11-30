import os
import re
import tempfile
import time
import gdown
import aiofiles
from async_executor.task import TaskState
from modules.service import Service
from pyrogram import emoji
from pyrogram.types import Message
from aiodav.client import Client as DavClient


class DriveService(Service):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    @staticmethod
    def check(m: Message):
        return bool(m.text) and bool(
            re.match(r"^https?:\/\/(www\.)?drive\.google\.com", m.text)
        )

    async def start(self) -> None:
        self.set_state(TaskState.STARTING)

        async with DavClient(
            hostname=self.webdav_hostname,
            login=self.webdav_username,
            password=self.webdav_password,
            timeout=self.timeout,
            chunk_size=2097152,
        ) as dav:
            with tempfile.TemporaryDirectory() as directory:
                link = self.kwargs.get("url", self.file_message.text)                

                self.reset_stats()
                self.set_state(
                    TaskState.WORKING,
                    description=f"{emoji.HOURGLASS_DONE} Downloading drive file",
                )

                name = f"google-drive-file-{time.time()}"
                path = os.path.join(directory, name)

                output = gdown.download(link, path, quiet=True)
                
                async with aiofiles.open(output, "rb") as file:
                    size = os.path.getsize(path)
                    await self.upload_file(dav, file, size)

