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
from humanize import naturalsize


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
            formats = meta.get('formats', [meta]) # Filter no-audio streams

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

    async def start(self) -> None:        
        try:
            # Chosen video format
            format = await self.options()
            if format is None:
                raise CancelledError
            format = format[0]

            self._set_state(TaskState.STARTING)

            def progress_wrapper(d):                   
                self._make_progress(d.get('downloaded_bytes', None), 
                                    d.get('total_bytes', None), 
                                    speed=d.get('speed', None), 
                                    eta=d.get('eta', None))

            options = {
                'format': f"{format['format_id']}+bestaudio",
                'quiet': True,
                'noplaylist' : True,
                'writesubtitles': True,
                'allsubtitles': True,
                'progress_hooks': [progress_wrapper]
            }
            
            with youtube_dl.YoutubeDL(options) as ydl:  
                self._set_state(TaskState.WORKING, description=f"{emoji.HOURGLASS_DONE} Downloading video")
                self.reset_stats()

                loop = asyncio.get_running_loop()
                meta = await loop.run_in_executor(None, 
                    functools.partial(ydl.extract_info, self.file_message.text, download=True))               
                filename = ydl.prepare_filename(meta)

            # Check if changed format
            if not os.path.exists(filename):
                filename, _ = os.path.splitext(filename)
                filename = filename + '.mkv'

            async with DavClient(hostname=self.webdav_hostname,
                                login=self.webdav_username,
                                password=self.webdav_password,
                                timeout=10 * 60 * 5,
                                chunk_size=2097152) as dav:
                await self.upload_file(dav, filename, os.stat(filename), title=meta['title'])
                self._set_state(TaskState.SUCCESSFULL)
        except CancelledError:
            self._set_state(TaskState.CANCELED, f"Task cancelled")
        except Exception as e:
            self._set_state(
                TaskState.ERROR,
                f"{emoji.CROSS_MARK} Error: {traceback.format_exc()}")
        finally:
            try:
                os.unlink(filename) # Delete file
            except Exception:
                pass

        return None
