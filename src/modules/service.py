import asyncio
import aiofiles
import utils
import os

from pyrogram.types import Message
from async_executor.task import Task, TaskState
from aiodav.client import Client as DavClient
from pyrogram import emoji
from asyncio.exceptions import CancelledError


class Service(Task):
    def __init__(
        self, id: int, user: int, file_message: Message, *args, **kwargs
    ) -> None:
        self.user = user
        self.file_message = file_message

        self.pyrogram = kwargs.get("pyrogram", file_message._client)
        self.split_size = kwargs.get("split_size", 100) * 1024 * 1024  # Bytes

        self.webdav_hostname = kwargs.get("hostname")
        self.webdav_username = kwargs.get("username")
        self.webdav_password = kwargs.get("password")
        self.webdav_path = kwargs.get("path")

        super().__init__(id, *args, **kwargs)

    @staticmethod
    def check(message: Message) -> bool:
        raise NotImplementedError

    async def upload_file(self, title: str, path: str, file_size: int, dav: DavClient):
        retry_count = 3
        split_size = self.split_size

        async with aiofiles.open(path, "rb") as file:
            if split_size <= 0:
                split_size = file_size
            pieces = file_size // split_size
            if file_size % split_size != 0:
                pieces += 1

            name = utils.sanitaze_filename(os.path.basename(path))
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
