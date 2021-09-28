import asyncio
import os
import re
import traceback
import aiofiles.tempfile
from asyncio.exceptions import CancelledError

import aiohttp
from aiodav.client import Client as DavClient
from aiohttp import ClientResponse
from pyrogram import emoji, filters
from pyrogram.types import Message

from async_executor.task import Task, TaskState
from modules.service import Service
from utils import URL_REGEX_PATTERN


class HttpService(Service):
    """
    Download web file and upload to webdav
    """

    # yapf: disable
    def __init__(
        self,
        id: int,
        user: int,
        file_message: Message,
        *args, **kwargs
    ) -> None:
        #yapf: enable
        super().__init__(id, user, file_message, *args, **kwargs)

    @staticmethod
    def check(m: Message):
        return bool(re.fullmatch(URL_REGEX_PATTERN, m.text))

    async def _streaming(self, filename: str, dav: DavClient,
                         response: ClientResponse):
        remote_path = os.path.join(self.webdav_path, filename)
        self._set_state(
            TaskState.WORKING,
            description=f'{emoji.HOURGLASS_DONE} Streaming to Webdav')

        async def file_sender():
            # TODO: delete this hardcode value
            offset = 0
            async for chunk in response.content.iter_chunked(2097152):
                offset += len(chunk)
                self._make_progress(offset, response.content_length)
                yield chunk

        await dav.upload_to(remote_path, buffer=file_sender())

    async def _upload_by_split(self, filename: str, dav: DavClient,
                               response: ClientResponse):
        async with aiofiles.tempfile.TemporaryFile() as file:
            async def upload_file(buffer_size, i):
                assert (await file.seek(0) == 0), "Impossible seek to start of stream"

                remote_path = os.path.join(self.webdav_path,
                                           f"{filename}.{i:0=3}")
                retry_count = 3

                while True:
                    try:
                        self._set_state(
                            TaskState.WORKING,
                            description=
                            f"{emoji.HOURGLASS_DONE} Uploading **Piece #{k}**")
                        self._make_progress(0, buffer_size)

                        await dav.upload_to(remote_path,
                                            buffer=file,
                                            buffer_size=buffer_size,
                                            progress=self._make_progress,
                                            progress_args=())
                        break
                    except CancelledError:
                        raise CancelledError
                    except Exception as e:
                        self._set_state(
                            TaskState.WORKING,
                            description=
                            f"{emoji.CLOCKWISE_VERTICAL_ARROWS} Trying again at error: {retry_count} attemps"
                        )
                        await asyncio.sleep(5)  # Wait

                        retry_count -= 1
                        if retry_count < 0:
                            raise e

                        assert (await file.seek(
                            0) == 0), "Impossible seek to start of stream"

                assert (await file.seek(0) == 0), "Impossible seek to start of stream"
                assert (await file.truncate(
                    0) == 0), "Impossible truncate temporary file"

            k = 0
            # TODO: delete this hardcode value
            offset = 0
            async for chunk in response.content.iter_chunked(2097152):
                self._set_state(
                    TaskState.WORKING,
                    description=f'{emoji.HOURGLASS_DONE} Downloading')
                offset += len(chunk)
                self._make_progress(offset, response.content_length)

                await file.write(chunk)
                await file.flush()

                # reach size limit
                length = await file.tell()
                if length >= self.split_size:
                    await upload_file(length, k)
                    k += 1

            # has some bytes still to write
            length = await file.tell()
            if length != 0:
                await upload_file(length, k)

    async def start(self) -> None:
        self._set_state(TaskState.STARTING)

        async with DavClient(hostname=self.webdav_hostname,
                             login=self.webdav_username,
                             password=self.webdav_password,
                             timeout=10 * 60 * 5,
                             chunk_size=2097152) as dav:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(self.file_message.text) as response:
                        filename = os.path.basename(self.file_message.text)

                        if self.split_size == 0:
                            await self._streaming(filename, dav, response)
                        else:
                            await self._upload_by_split(
                                filename, dav, response)

                self._set_state(TaskState.SUCCESSFULL)
            except CancelledError:
                self._set_state(TaskState.CANCELED, f"Task cancelled")
            except Exception as e:
                self._set_state(
                    TaskState.ERROR,
                    f"{emoji.CROSS_MARK} Error: {traceback.format_exc()}")

        return None
