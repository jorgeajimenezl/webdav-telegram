import asyncio
import aiofiles
import utils
import os
import aiofiles.tempfile

from pyrogram.types import Message
from async_executor.task import Task, TaskState
from aiodav.client import Client as DavClient
from pyrogram import emoji
from asyncio.exceptions import CancelledError
from typing import AsyncGenerator, Union
from io import IOBase


class Service(Task):
    def __init__(
        self, id: int, user: int, file_message: Message, *args, **kwargs
    ) -> None:
        self.user = user
        self.file_message = file_message

        self.pyrogram = kwargs.get("pyrogram", file_message._client)
        self.split_size = kwargs.get("split_size", 100) * 1024 * 1024  # Bytes
        self.use_streaming = kwargs.get("streaming", False)

        self.webdav_hostname = kwargs.get("hostname")
        self.webdav_username = kwargs.get("username")
        self.webdav_password = kwargs.get("password")
        self.webdav_path = kwargs.get("path")

        super().__init__(id, *args, **kwargs)

    @staticmethod
    def check(message: Message) -> bool:
        raise NotImplementedError

    async def copy(
        self,
        dav: DavClient,
        filename: str,
        total_bytes: int,
        generator: AsyncGenerator[bytes, None],
    ):
        async with aiofiles.tempfile.TemporaryFile() as file:
            self._set_state(
                TaskState.WORKING,
                description=f"{emoji.HOURGLASS_DONE} Downloading to local filesystem",
            )
            self.reset_stats()
            offset = 0

            async for chunk in generator:
                offset += len(chunk)
                self._make_progress(offset, total_bytes)
                await file.write(chunk)

            await file.flush()
            await self.upload_file(
                dav,
                file,
                total_bytes,
                filename=filename,
            )

    async def streaming(
        self,
        dav: DavClient,
        filename: str,
        total_bytes: int,
        generator: AsyncGenerator[bytes, None],
    ):
        name = utils.sanitaze_filename(filename)
        remote_path = os.path.join(self.webdav_path, name)
        self._set_state(
            TaskState.WORKING, description=f"{emoji.HOURGLASS_DONE} Streaming to Webdav"
        )
        self.reset_stats()

        async def file_sender():
            offset = 0

            async for chunk in generator:
                offset += len(chunk)
                self._make_progress(offset, total_bytes)
                yield chunk

        await dav.upload_to(remote_path, buffer=file_sender())

    async def streaming_by_pieces(
        self,
        dav: DavClient,
        filename: str,
        total_bytes: int,
        generator: AsyncGenerator[bytes, None],
    ):
        async with aiofiles.tempfile.TemporaryFile() as file:
            k = 1
            offset = 0

            async for chunk in generator:
                self._set_state(
                    TaskState.WORKING, description=f"{emoji.HOURGLASS_DONE} Downloading"
                )

                offset += len(chunk)
                self._make_progress(offset, total_bytes)

                await file.write(chunk)

                # reach size limit
                length = await file.tell()
                if length >= self.split_size:
                    await file.flush()
                    await self.upload_file(
                        dav,
                        file,
                        length,
                        filename=f"{filename}.{k:0=3}",
                        title=f"{filename} (Piece #{k})",
                    )

                    assert await file.seek(0) == 0, "Impossible seek to start of stream"
                    assert (
                        await file.truncate(0) == 0
                    ), "Impossible truncate temporary file"
                    k += 1

                    self.reset_stats()

            # has some bytes still to write
            length = await file.tell()
            if length != 0:
                await file.flush()
                await self.upload_file(
                    dav,
                    file,
                    length,
                    filename=f"{filename}.{k:0=3}",
                    title=f"{filename} (Piece #{k})",
                )

                assert await file.seek(0) == 0, "Impossible seek to start of stream"
                assert await file.truncate(0) == 0, "Impossible truncate temporary file"

    async def upload_file(
        self,
        dav: DavClient,
        file: Union[str, IOBase],
        file_size: int,
        title: str = None,
        filename: str = None,
    ):
        retry_count = 3
        split_size = self.split_size

        if isinstance(file, str):
            file = aiofiles.open(file, "rb")
        else:
            file.__aenter__ = lambda x: x
            file.__aexit__ = lambda *args: None

        async with file:
            if split_size <= 0:
                split_size = file_size
            pieces = file_size // split_size
            if file_size % split_size != 0:
                pieces += 1

            filename = filename or os.path.basename(file)
            name = utils.sanitaze_filename(filename)
            title = title or name
            remote_path = os.path.join(self.webdav_path, name)

            for piece in range(pieces):
                while True:
                    try:
                        remote_name = (
                            f"{name}.{(piece + 1):0=3}" if pieces != 1 else name
                        )
                        remote_path = os.path.join(self.webdav_path, remote_name)

                        pos = await file.seek(piece * split_size)
                        assert pos == piece * split_size, "Impossible seek stream"
                        length = min(split_size, file_size - pos)

                        self._set_state(
                            TaskState.WORKING,
                            description=f"{emoji.HOURGLASS_DONE} Uploading **{title}**",
                        )
                        self.reset_stats()
                        self._make_progress(0, length)
                        await dav.upload_to(
                            remote_path,
                            buffer=file,
                            buffer_size=length,
                            progress=self._make_progress,
                        )
                        break
                    except CancelledError:
                        raise CancelledError
                    except Exception as e:
                        self._set_state(
                            TaskState.WORKING,
                            description=f"{emoji.CLOCKWISE_VERTICAL_ARROWS} Trying again at error: {retry_count} attemps",
                        )

                        await asyncio.sleep(5)  # Wait
                        retry_count -= 1
                        if retry_count < 0:
                            raise e
