import asyncio
import os
import tempfile
import traceback
from asyncio.exceptions import CancelledError

from aiodav.client import Client as DavClient
from pyrogram import emoji, filters
from pyrogram.types import Message

from async_executor.task import Task, TaskState
from modules.service import Service


class TelegramService(Service):
    """
    Download telegram file and upload to webdav
    """

    #yapf: disable
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
        return bool(m.document) | bool(m.photo) | bool(m.video) | bool(m.audio)

    def __get_file_name(message: Message):
        available_media = ("audio", "document", "photo", "sticker",
                           "animation", "video", "voice", "video_note",
                           "new_chat_photo")

        if isinstance(message, Message):
            for kind in available_media:
                media = getattr(message, kind, None)

                if media is not None:
                    break
            else:
                raise ValueError(
                    "This message doesn't contain any downloadable media")
        else:
            media = message

        return getattr(media, "file_name", "unknown")

    async def _streaming(self, filename: str, dav: DavClient):
        remote_path = os.path.join(self.webdav_path, filename)
        self._set_state(
            TaskState.WORKING,
            description=
            f'{emoji.HOURGLASS_DONE} Streaming from Telegram to Webdav')

        async def file_sender():
            async for chunk, offset, total in self.file_message.iter_download(
            ):
                self._make_progress(offset, total)
                yield chunk

        await dav.upload_to(remote_path, buffer=file_sender())

    async def _upload_by_split(self, filename: str, dav: DavClient):
        with tempfile.TemporaryFile() as file:

            async def upload_file(buffer_size, i):
                assert file.seek(0) == 0, "Impossible seek to start of stream"

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

                        assert file.seek(
                            0) == 0, "Impossible seek to start of stream"

                assert file.seek(0) == 0, "Impossible seek to start of stream"
                assert file.truncate(
                    0) == 0, "Impossible truncate temporary file"

            k = 0
            async for chunk, offset, total in self.file_message.iter_download(
            ):
                self._set_state(
                    TaskState.WORKING,
                    description=
                    f'{emoji.HOURGLASS_DONE} Downloading from Telegram')
                self._make_progress(offset, total)

                file.write(chunk)
                file.flush()

                # reach size limit
                if file.tell() >= self.split_size:
                    await upload_file(file.tell(), k)
                    k += 1

            # has some bytes still to write
            if file.tell() != 0:
                await upload_file(file.tell(), k)

    async def start(self) -> None:
        self._set_state(TaskState.STARTING)
        filename = TelegramService.__get_file_name(self.file_message)

        async with DavClient(hostname=self.webdav_hostname,
                             login=self.webdav_username,
                             password=self.webdav_password,
                             timeout=10 * 60 * 5,
                             chunk_size=2097152) as dav:
            try:
                if self.split_size == 0:
                    await self._streaming(filename, dav)
                else:
                    await self._upload_by_split(filename, dav)

                self._set_state(TaskState.SUCCESSFULL)
            except CancelledError:
                self._set_state(TaskState.CANCELED, f"Task cancelled")
            except Exception as e:
                self._set_state(
                    TaskState.ERROR,
                    f"{emoji.CROSS_MARK} Error: {traceback.format_exc()}")

        return None