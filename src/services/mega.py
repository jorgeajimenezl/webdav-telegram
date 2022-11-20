import re
import os
import aiofiles
import tempfile

from aiomega import Mega
from aiodav.client import Client as DavClient
from pyrogram import emoji
from async_executor.task import TaskState
from modules.service import Service
from pyrogram.types import Message


class MegaService(Service):
    """
    Download Mega file and upload to webdav
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    @staticmethod
    def check(m: Message):
        return bool(m.text) and bool(re.match(r"^https?:\/\/(www\.)?mega\.nz", m.text))

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
                async with Mega("ox8xnQZL") as mega:
                    link = self.kwargs.get("url", self.file_message.text)
                    node = await mega.get_public_node(link)
                    if not node.isFile():
                        raise Exception("Only can download files")

                    async def progress(c, t, s):
                        self.make_progress(c, t, speed=s)

                    self.reset_stats()
                    filename = node.getName()
                    size = node.getSize()
                    self.set_state(
                        TaskState.WORKING,
                        description=f"{emoji.HOURGLASS_DONE} Download {filename}",
                    )
                    
                    # Fix bug
                    directory = f"{directory}/" if directory[-1] != "/" else directory
                    await mega.download(node, os.pat, progress=progress)

                path = os.path.join(directory, filename)
                async with aiofiles.open(path, "rb") as file:
                    await self.upload_file(dav, file, size)

        return None
