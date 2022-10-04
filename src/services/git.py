import asyncio
import re
import tempfile
import os
import utils
import aiofiles

from async_executor.task import TaskState
from modules.service import Service
from pyrogram import emoji
from pyrogram.types import Message
from aiodav.client import Client as DavClient


class GitService(Service):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    @staticmethod
    def check(m: Message):
        return bool(m.text) and bool(
            re.fullmatch(
                r"((git|ssh|http(s)?)|(git@[\w\.]+))(:(//)?)([\w\.@\:/\-~]+)(\.git)(/)?",
                m.text,
            )
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
            url = self.kwargs.get("url", self.file_message.text)
            filename = os.path.basename(url).removesuffix(".git")

            self.set_state(
                TaskState.WORKING,
                description=f"{emoji.HOURGLASS_DONE} Cloning the repository",
            )

            with tempfile.TemporaryDirectory() as directory:
                path = os.path.join(directory, "repo")

                # Cloning the repository
                await utils.execute_process("git", "clone", url, path)

                self.set_state(
                    TaskState.WORKING,
                    description=f"{emoji.HOURGLASS_DONE} Compressing the repository",
                )

                # Archiving file
                await utils.execute_process(
                    "tar",
                    "-cf",
                    f"{path}.tar",
                    path,
                )

                file_size = os.path.getsize(f"{path}.tar")
                async with aiofiles.open(f"{path}.tar", "rb") as file:
                    await self.upload_file(dav, file, file_size, filename=filename)
