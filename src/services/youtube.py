import asyncio
import os
import aiofiles
import yt_dlp
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
        *args, **kwargs
    ) -> None:
        #yapf: enable
        super().__init__(id, *args, **kwargs)

    @staticmethod
    def check(m: Message):
        if not bool(m.text):
            return False

        extractors = yt_dlp.extractor.gen_extractors()
        for e in extractors:
            if e.suitable(m.text) and e.IE_NAME != 'generic':
                return True
        return False
        
    async def options(self) -> str:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            loop = asyncio.get_running_loop()
            link = self.kwargs.get('url', self.file_message.text)
            meta = await loop.run_in_executor(None, 
                functools.partial(ydl.extract_info, link, download=False))
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
            
            with yt_dlp.YoutubeDL(options) as ydl:  
                self._set_state(TaskState.WORKING, description=f"{emoji.HOURGLASS_DONE} Downloading video")
                self.reset_stats()

                loop = asyncio.get_running_loop()
                link = self.kwargs.get('url', self.file_message.text)
                meta = await loop.run_in_executor(None, 
                    functools.partial(ydl.extract_info, link, download=True))               
                filename = ydl.prepare_filename(meta)

            # Check if changed format
            if not os.path.exists(filename):
                filename, _ = os.path.splitext(filename)
                filename = filename + '.mkv'

            async with DavClient(hostname=self.webdav_hostname,
                                login=self.webdav_username,
                                password=self.webdav_password,
                                timeout=self.timeout,
                                chunk_size=2097152) as dav:
                async with aiofiles.open(filename, 'rb') as file:
                    await self.upload_file(dav, file, os.stat(filename).st_size, title=meta['title'])
        except Exception as e:
            raise e
        finally:
            try:
                os.unlink(filename) # Delete file
            except Exception:
                pass

        return None
