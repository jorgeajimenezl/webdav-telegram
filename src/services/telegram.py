from typing import Tuple

from datetime import datetime as dt
from aiodav.client import Client as DavClient
from async_executor.task import TaskState
from modules.service import Service
from pyrogram import emoji
from pyrogram.types import Message


class TelegramService(Service):
    """
    Download telegram file and upload to webdav
    """

    def __init__(self, id: int, *args, **kwargs) -> None:
        super().__init__(id, *args, **kwargs)

    @staticmethod
    def check(m: Message):
        return bool(m.document) | bool(m.photo) | bool(m.video) | bool(m.audio)

    def __get_file_name(message: Message) -> Tuple[str, int]:
        available_media = (
            "audio",
            "document",
            "photo",
            "sticker",
            "animation",
            "video",
            "voice",
            "video_note",
            "new_chat_photo",
        )

        if isinstance(message, Message):
            for kind in available_media:
                media = getattr(message, kind, None)

                if media is not None:
                    break
            else:
                raise ValueError("This message doesn't contain any downloadable media")
        else:
            media = message

        return (getattr(media, "file_name", None), getattr(media, "file_size", None))

    async def start(self) -> None:
        self._set_state(TaskState.STARTING)
        filename, total_bytes = TelegramService.__get_file_name(self.file_message)

        if filename is None:
            filename = f"file-{str(dt.now()).replace(' ', '-')}"

        async with DavClient(
            hostname=self.webdav_hostname,
            login=self.webdav_username,
            password=self.webdav_password,
            timeout=self.timeout,
            chunk_size=2097152,
        ) as dav:

            async def gen():
                async for chunk in self.pyrogram.stream_media(self.file_message):
                    yield chunk

            await self.upload(
                dav,
                filename,
                total_bytes,
                gen(),
            )

        return None
