from asyncio.exceptions import CancelledError
from task import Task, TaskState
from pyrogram import emoji
from pyrogram.types import Message

import traceback, tempfile, asyncio, os, aiofiles
from aiodav.client import Client as DavClient


class TelegramToWebdavParallelTask(Task):
    """
    Download telegram file and upload to webdav
    """
    def __init__(self, id: int, user: int, *args, **kwargs) -> None:
        super().__init__(id, *args, **kwargs)

        self.user = user
        self.file_message = kwargs.get('file_message')
        self.split_size = kwargs.get('split_size', 10) * 1024 * 1024  # Bytes

        self.webdav_hostname = kwargs.get('hostname')
        self.webdav_username = kwargs.get('username')
        self.webdav_password = kwargs.get('password')
        self.webdav_path = kwargs.get('path')
        
        # self.executor = kwargs.get('executor')

    def __get_file_name(message):
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

    async def _upload(self, filename: str, dav: DavClient):
        with tempfile.TemporaryDirectory() as directory:
            k = 1
            piece = open(os.path.join(directory, f"{filename}.{k:0=3}"), "wb")
            self.total_upload = 0

            async for chunk, offset, total in self.file_message.iter_download():
                self.total_upload = total
                self._set_state(
                    TaskState.WORKING,
                    description=
                    f'{emoji.HOURGLASS_DONE} Downloading from Telegram')
                self._make_progress(offset, total)

                piece.write(chunk)

                # reach size limit
                if piece.tell() >= self.split_size:
                    piece.close()
                    k += 1

                    piece = open(os.path.join(directory, f"{filename}.{k:0=3}"), "wb")

            if piece.tell() != 0:
                piece.close()

            M = [0] * (k + 1)
            self.current_upload = 0

            # Upload in parallel
            async def upload_file(i: int):
                retry_count = 3                

                def progress(current, total):
                    self.current_upload -= M[i]
                    self.current_upload += current
                    M[i] = current

                    self._make_progress(self.current_upload, self.total_upload)

                path = os.path.join(directory, f"{filename}.{i:0=3}")
                async with aiofiles.open(path, "rb") as file:
                    buffer_size = os.stat(path).st_size
                    while True:
                        try:
                            remote_path = os.path.join(self.webdav_path,
                                           f"{filename}.{i:0=3}")

                            await dav.upload_to(remote_path,
                                                buffer=file,
                                                buffer_size=buffer_size,
                                                progress=progress)
                            break
                        except CancelledError:
                            raise CancelledError
                        except Exception as e:
                            await asyncio.sleep(5)  # Wait
                            retry_count -= 1
                            if retry_count < 0:
                                raise e
                            assert (await file.seek(
                                0) == 0), "Impossible seek to start of stream"
                return i

            try:
                # schedule all uploads to do *concurrently*
                self._set_state(
                            TaskState.WORKING,
                            description=
                            f"{emoji.HOURGLASS_DONE} Uploading all pieces")
                            
                self._make_progress(0, self.total_upload)
                coros = [upload_file(i) for i in range(1, k + 1)]
                L = await asyncio.gather(*coros)
            except Exception:
                self.cancel()

    async def start(self) -> None:
        self._set_state(TaskState.STARTING)
        filename = TelegramToWebdavParallelTask.__get_file_name(self.file_message)

        async with DavClient(hostname=self.webdav_hostname,
                             login=self.webdav_username,
                             password=self.webdav_password,
                             timeout=10 * 60,
                             chunk_size=2097152) as dav:
            try:
                if self.split_size == 0:
                    self.split_size = (1 << 40)
                
                await self._upload(filename, dav)
                self._set_state(TaskState.SUCCESSFULL)
            except CancelledError:
                self._set_state(TaskState.CANCELED, f"Task cancelled")
            except Exception as e:
                self._set_state(
                    TaskState.ERROR,
                    f"{emoji.CROSS_MARK} Error: {traceback.format_exc()}")

        return None