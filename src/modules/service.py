import asyncio
import aiofiles
import utils
import os

# import aiofiles.tempfile
import tempfile

from pyrogram.types import Message
from aiofiles.threadpool.binary import AsyncBufferedIOBase
from async_executor.task import Task, TaskState
from aiodav.client import Client as DavClient
from pyrogram import emoji, Client
from asyncio.exceptions import CancelledError
from typing import AsyncGenerator
from io import IOBase
from Cryptodome.Hash import SHA1


class Service(Task):
    def __init__(self, id: int, *args, **kwargs) -> None:
        self.user: int = kwargs.get("user")
        self.file_message: Message = kwargs.get("file_message")

        self.pyrogram: Client = kwargs.get("pyrogram", self.file_message._client)
        self.split_size: int = kwargs.get("split_size", 100) * 1024 * 1024  # Bytes
        self.use_streaming: bool = kwargs.get("streaming", False)
        self.parallel: bool = kwargs.get("parallel", False)
        self.checksum: bool = kwargs.get("checksum", True)

        if self.checksum:
            self.sha1 = None
            self.sums = dict()

        self.webdav_hostname: str = kwargs.get("hostname")
        self.webdav_username: str = kwargs.get("username")
        self.webdav_password: str = kwargs.get("password")
        self.webdav_path: str = kwargs.get("path")
        self.timeout: int = kwargs.get("timeout", 60 * 60 * 2)

        super().__init__(id, *args, **kwargs)

    @staticmethod
    def check(message: Message) -> bool:
        raise NotImplementedError

    def get_pieces_count(self, file_size: int) -> int:
        if file_size == None:
            return None

        split_size = self.split_size if self.split_size > 0 else file_size
        pieces = file_size // split_size
        if file_size % split_size != 0:
            pieces += 1

        return pieces

    def upload(self, *args, **kwargs):
        if self.parallel:
            func = self.copy if self.split_size <= 0 else self.streaming
        if self.use_streaming:
            func = self.streaming if self.split_size <= 0 else self.streaming_by_pieces
        else:
            func = self.copy
        return func(*args, **kwargs)

    async def upload_parallel(
        self,
        dav: DavClient,
        filename: str,
        file_size: int,
        generator: AsyncGenerator[bytes, None],
    ):
        with tempfile.TemporaryDirectory() as directory:
            k = 1
            offset = 0
            files = [os.path.join(directory, f"{k}")]
            file = open(files[-1], "wb")

            self._set_state(
                TaskState.WORKING, description=f"{emoji.HOURGLASS_DONE} Downloading"
            )
            async for chunk in generator:
                offset += len(chunk)
                self._make_progress(offset, file_size)

                file.write(chunk)

                # reach size limit
                length = file.tell()
                if length >= self.split_size:
                    file.close()

                    # Change to the next file
                    files.append(os.path.join(directory, f"{k}"))
                    file = open(files[-1], "wb")

            async def get_file(path):
                async with aiofiles.open(path, "rb") as f:
                    length = os.stat(path).st_size
                    await self.upload_file(
                        dav, f, length, filename=f"{filename}.{k:0=3}"
                    )
                try:
                    os.unlink(path)
                except Exception:
                    pass

            await asyncio.gather([get_file(x) for x in files])

    async def copy(
        self,
        dav: DavClient,
        filename: str,
        file_size: int,
        generator: AsyncGenerator[bytes, None],
    ) -> None:
        """Download the whole file before to send it to the webdav server"""

        with tempfile.TemporaryFile() as file:
            self._set_state(
                TaskState.WORKING,
                description=f"{emoji.HOURGLASS_DONE} Downloading to local filesystem",
            )
            self.reset_stats()
            offset = 0

            async for chunk in generator:
                offset += len(chunk)
                self._make_progress(offset, file_size)
                file.write(chunk)

            file.flush()
            await self.upload_file(
                dav,
                file,
                (file_size or offset),
                filename=filename,
            )

    async def streaming(
        self,
        dav: DavClient,
        filename: str,
        file_size: int,
        generator: AsyncGenerator[bytes, None],
    ) -> None:
        """Stream from the generator to webdav server"""

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
                self._make_progress(offset, file_size)

                if self.checksum:
                    self.sha1.update(chunk)

                yield chunk

        if self.checksum:
            self.sha1 = SHA1.new()

        await dav.upload_to(remote_path, buffer=file_sender())

        if self.checksum:
            self.sums[name] = self.sha1.hexdigest()

    async def streaming_by_pieces(
        self,
        dav: DavClient,
        filename: str,
        file_size: int,
        generator: AsyncGenerator[bytes, None],
    ) -> None:
        """Download a small piece with specified size and upload it"""
        with tempfile.TemporaryFile() as file:
            k = 1
            offset = 0
            pieces = self.get_pieces_count(file_size)

            async for chunk in generator:
                self._set_state(
                    TaskState.WORKING, description=f"{emoji.HOURGLASS_DONE} Downloading"
                )

                offset += len(chunk)
                self._make_progress(offset, file_size)

                file.write(chunk)

                # reach size limit
                length = file.tell()
                if length >= self.split_size:
                    file.flush()
                    await self.upload_file(
                        dav,
                        file,
                        length,
                        filename=f"{filename}.{k:0=3}",
                        title=f"{filename} [Piece #{k}]"
                        if pieces == None
                        else f"{filename} [{k}/{pieces}]",
                    )

                    assert file.seek(0) == 0, "Impossible seek to start of stream"
                    assert file.truncate(0) == 0, "Impossible truncate temporary file"
                    k += 1

                    self.reset_stats()

            # has some bytes still to write
            length = file.tell()
            if length != 0:
                file.flush()
                await self.upload_file(
                    dav,
                    file,
                    length,
                    filename=f"{filename}.{(k + 1):0=3}" if pieces != 1 else filename,
                    title=f"{filename} [Piece #{k}]"
                    if pieces == None
                    else f"{filename} [{k}/{pieces}]",
                )

                assert file.seek(0) == 0, "Impossible seek to start of stream"
                assert file.truncate(0) == 0, "Impossible truncate temporary file"

    async def upload_file(
        self,
        dav: DavClient,
        file: IOBase,
        file_size: int,
        title: str = None,
        filename: str = None,
    ) -> None:
        """Upload a file to webdav. If the file need to split, this split it"""
        retry_count = 3

        split_size = self.split_size if self.split_size > 0 else file_size
        pieces = self.get_pieces_count(file_size)

        filename = filename or os.path.basename(file.name)
        name = utils.sanitaze_filename(filename)
        title = title or name
        remote_path = os.path.join(self.webdav_path, name)

        for piece in range(pieces):
            while True:  # Try loop
                try:
                    remote_name = f"{name}.{(piece + 1):0=3}" if pieces != 1 else name
                    remote_path = os.path.join(self.webdav_path, remote_name)

                    pos = (
                        (await file.seek(piece * split_size))
                        if isinstance(file, AsyncBufferedIOBase)
                        else file.seek(piece * split_size)
                    )
                    assert pos == piece * split_size, "Impossible seek stream"
                    length = min(split_size, file_size - pos)

                    self._set_state(
                        TaskState.WORKING,
                        description=f"{emoji.HOURGLASS_DONE} Uploading **{title} [{piece}/{pieces}]**",
                    )
                    self.reset_stats()
                    self._make_progress(0, length)
                    await dav.upload_to(
                        remote_path,
                        buffer=file,
                        buffer_size=length,
                        progress=self._make_progress,
                    )

                    if self.checksum:
                        # Compute the piece checksum
                        assert (
                            (await file.seek(piece * split_size))
                            if isinstance(file, AsyncBufferedIOBase)
                            else file.seek(piece * split_size)
                        ) == piece * split_size, "Impossible seek stream"
                        self.sha1 = SHA1.new()

                        while length > 0:
                            size = min(length, 65535)
                            data = (
                                await file.read(size)
                                if isinstance(file, AsyncBufferedIOBase)
                                else file.read(size)
                            )
                            self.sha1.update(data)
                            length -= len(data)

                        self.sums[remote_name] = self.sha1.hexdigest()

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
