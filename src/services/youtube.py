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
from humanize import naturalsize, naturaldelta


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
        extractors = youtube_dl.extractor.gen_extractors()
        for e in extractors:
            if e.suitable(m.text) and e.IE_NAME != 'generic':
                return True
        return False
        
    async def options(self) -> str:
        with youtube_dl.YoutubeDL({'quiet': True}) as ydl:
            loop = asyncio.get_running_loop()

            meta = await loop.run_in_executor(None, 
                functools.partial(ydl.extract_info, self.file_message.text, download=False))
            formats = meta.get('formats', [meta])
            formats = [x for x in formats if x['acodec'] != 'none'] # Filter no-audio streams

            app = self.pyrogram
            format = await utils.selection(
                app,
                self.user,
                options=formats,
                message_text='**Select format**',
                multi_selection=False,
                name_selector=lambda x: f"{ydl.format_resolution(x)}({x['ext']}) - "
                                        f"{naturalsize(x['filesize'], binary=True) if 'filesize' in x and x['filesize'] != None else 'Unknown'}")

            return format

    async def upload_file(self, path: str, buffer_size: int, dav: DavClient, split_size: int = -1):
        retry_count = 3
        async with aiofiles.open(path, "rb") as file:
            if split_size == -1:
                split_size = buffer_size
            pieces = buffer_size // split_size
            if buffer_size % split_size != 0:
                pieces += 1

            name = os.path.basename(path)
            remote_path = os.path.join(self.webdav_path, name)

            for piece in range(pieces):
                while True:
                    try:
                        pos = await file.seek(piece * split_size)
                        assert pos != piece * split_size, "Impossible seek stream"
                        length = min(split_size, buffer_size - pos)                        

                        self._make_progress(0, length)
                        await dav.upload_to(remote_path,
                                            buffer=file,
                                            buffer_size=length,
                                            progress=self._make_progress)
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

    async def start(self) -> None:        
        try:
            # Chosen video format
            format = await self.options()
            if format is None:
                raise CancelledError
            format = format[0]

            self._set_state(TaskState.STARTING)

            def progress_wrapper(d):
                eta = d.get('eta', None)
                if eta != None:
                    self._set_state(TaskState.WORKING, description=f"{emoji.HOURGLASS_DONE} Downloading video (ETA: {naturaldelta(eta)})")
                self._make_progress(d.get('downloaded_bytes', None), d.get('total_bytes', None))

            options = {
                'format': format['format_id'],
                'quiet': True,
                'noplaylist' : True,
                'writesubtitles': True,
                'allsubtitles': True,
                'progress_hooks': [progress_wrapper]
            }
            
            with youtube_dl.YoutubeDL(options) as ydl:  
                self._set_state(TaskState.WORKING, description=f"{emoji.HOURGLASS_DONE} Downloading video")

                loop = asyncio.get_running_loop()
                meta = await loop.run_in_executor(None, 
                    functools.partial(ydl.extract_info, self.file_message.text, download=True))               
                filename = ydl.prepare_filename(meta)

            async with DavClient(hostname=self.webdav_hostname,
                                login=self.webdav_username,
                                password=self.webdav_password,
                                timeout=10 * 60 * 5,
                                chunk_size=1048576) as dav:
                self._set_state(TaskState.WORKING,
                                description=
                                f"{emoji.HOURGLASS_DONE} Uploading **{meta['title']}**")
                await self.upload_file(filename, os.stat(filename).st_size, dav, self.split_size)
                os.unlink(filename) # Delete file

                self._set_state(TaskState.SUCCESSFULL)
        except CancelledError:
            self._set_state(TaskState.CANCELED, f"Task cancelled")
        except Exception as e:
            self._set_state(
                TaskState.ERROR,
                f"{emoji.CROSS_MARK} Error: {traceback.format_exc()}")

        return None
