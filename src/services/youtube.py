import asyncio
import os
import re
import traceback
import aiofiles
import youtube_dl
import functools
from asyncio.exceptions import CancelledError

from aiodav.client import Client as DavClient

from pyrogram import emoji
from pyrogram.types import Message

import utils
from async_executor.task import TaskState
from modules.service import Service
from filesize import naturalsize


class YoutubeService(Service):
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
        # TODO: Improve this regex
        return bool(m.text) and re.fullmatch(
            rf'https?:\/\/(www\.)?(youtu\.be|youtube\.com)\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)',
            m.text)

    async def options(self) -> str:
        with youtube_dl.YoutubeDL({'quiet': True}) as ydl:
            loop = asyncio.get_running_loop()
            func = functools.partial(ydl.extract_info, self.file_message.text, download=False)

            meta = await loop.run_in_executor(None, func)
            formats = meta.get('formats', [meta])

            app = self.pyrogram
            format = await utils.selection(
                app,
                self.user,
                options=formats,
                message_text='**Select format**',
                multi_selection=False,
                name_selector=lambda x: f"{ydl.format_resolution(x)}({x['ext']}) - "
                                        f"{naturalsize(x['filesize'], binary=True) if 'filesize' in x else 'Unknown'}")

            return format

    async def upload_file(self, path: str, buffer_size: int, dav: DavClient):
        retry_count = 3
        async with aiofiles.open(path, "rb") as file:
            while True:
                try:
                    name = os.path.basename(path)
                    remote_path = os.path.join(self.webdav_path, name)

                    await dav.upload_to(remote_path,
                                        buffer=file,
                                        buffer_size=buffer_size,
                                        progress=self._make_progress)
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

    async def start(self) -> None:        
        try:
            # Chosen video format
            format = await self.options()
            if format is None:
                raise CancelledError
            format = format[0]

            self._set_state(TaskState.STARTING)

            def progress_wrapper(d):
                self._make_progress(d['downloaded_bytes'], d['total_bytes_estimate'])

            options = {
                'format': format['format_id'],
                'quiet': True,
                'noplaylist' : True,
                'writesubtitles': True,
                'allsubtitles': True,
                'progress_hooks': [progress_wrapper]
            }
            
            with youtube_dl.YoutubeDL(options) as ydl:
                loop = asyncio.get_running_loop()
                func = functools.partial(ydl.extract_info, self.file_message.text, download=True)

                self._set_state(TaskState.WORKING,
                                description=
                                f"{emoji.HOURGLASS_DONE} Downloading video")

                meta = await loop.run_in_executor(None, func)               
                filename = ydl.prepare_filename(meta)

            async with DavClient(hostname=self.webdav_hostname,
                                login=self.webdav_username,
                                password=self.webdav_password,
                                timeout=10 * 60 * 5,
                                chunk_size=2097152) as dav:
                self._set_state(TaskState.WORKING,
                                description=
                                f"{emoji.HOURGLASS_DONE} Upload {os.path.basename(filename)} to webdav server")
                self.upload_file(filename, os.stat(filename).st_size, dav)
                os.unlink(filename) # Delete file

                self._set_state(TaskState.SUCCESSFULL)
        except CancelledError:
            self._set_state(TaskState.CANCELED, f"Task cancelled")
        except Exception as e:
            self._set_state(
                TaskState.ERROR,
                f"{emoji.CROSS_MARK} Error: {traceback.format_exc()}")

        return None
