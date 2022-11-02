import os
import re
import tempfile
from urllib.parse import urlparse
import aiohttp
import aiofiles
import utils

from async_executor.task import TaskState
from modules.service import Service
from pyrogram import emoji
from pyrogram.types import Message
from aiodav.client import Client as DavClient


class URLBatchService(Service):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    @staticmethod
    def check(m: Message):
        return bool(m.document) and m.document.file_name.startswith("urlbatch")

    async def start(self) -> None:
        self.set_state(TaskState.STARTING)

        with (await self.file_message.download(in_memory=True)) as file:
            urls = file.readlines()
            urls = list(
                set([url.decode() for url in urls if re.match(rb"^https?://", url)])
            )

        with tempfile.TemporaryDirectory() as directory:
            async with aiohttp.ClientSession() as session:
                for url in urls:
                    async with session.get(url) as response:
                        try:
                            d = response.headers["content-disposition"]
                            filename = re.findall("filename=(.+)", d)[0].split(";")[0]
                        except Exception:
                            req = urlparse(url)
                            filename = os.path.basename(req.path)

                        self.set_state(
                            TaskState.WORKING, description=f"{emoji.HOURGLASS_DONE} Downloading {filename}"
                        )

                        # Download file
                        async with aiofiles.open(
                            os.path.join(directory, filename), "wb"
                        ) as f:
                            async for chunk in response.content.iter_chunked(2097152):
                                await f.write(chunk)

            # Compress files with tar
            with tempfile.NamedTemporaryFile() as tar:
                self.set_state(
                    TaskState.WORKING,
                    description=f"{emoji.HOURGLASS_DONE} Compressing the repository",
                )

                await utils.execute_process(
                    "tar",
                    "-cf",
                    tar.name,
                    ".",
                    cwd=directory,
                )

                # Upload file to WebDAV
                async with DavClient(
                    hostname=self.webdav_hostname,
                    login=self.webdav_username,
                    password=self.webdav_password,
                    timeout=self.timeout,
                    chunk_size=2097152,
                ) as dav:
                    await self.upload_file(
                        dav,
                        tar,
                        os.path.getsize(tar.name),
                        filename=f"batch-{self.file_message.id}.tar",
                    )
