import asyncio
import os
import re
import aiofiles

import aria2p
import utils
from aiodav.client import Client as DavClient
from async_executor.task import TaskState
from modules.service import Service
from pyrogram import emoji
from pyrogram.types import Message


class TorrentService(Service):
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
        # TODO: Improve this regex
        return bool(m.text) and bool(re.match(
            rf'magnet:\?xt=urn:[a-z0-9]+:[a-zA-Z0-9]+',
            m.text))

    async def options(self, aria2: aria2p.API) -> None:       
        link = self.kwargs.get('url', self.file_message.text)
        d = aria2.add_magnet(link,
                             options={
                                 'bt-metadata-only': 'true',
                                 'bt-save-metadata': 'true'
                             })        

        # Wait while get download information
        while not d.is_complete:
            await asyncio.sleep(0.5)
            d.update()

            if d.status == 'error':
                await self.pyrogram.send_message(
                    self.user,
                    f"{emoji.CROSS_MARK} Unable to download metadata information from magnet link"
                )
                break

        d = aria2.add_torrent(f'/app/data/{d.info_hash}.torrent',
                              options={'dry-run': 'true'})

        app = self.pyrogram
        files = await utils.selection(
            app,
            self.user,
            options=d.files,
            message_text='**Select files to download**',
            name_selector=lambda x: os.path.basename(x.path))

        return d.info_hash, [p.index for p in files]

    async def start(self) -> None:
        aria2 = aria2p.API(aria2p.Client(host="http://127.0.0.1"))

        # Chossing torrent files to download            
        info_hash, files = await self.options(aria2)       

        self._set_state(TaskState.STARTING)    
        # link = self.kwargs.get('url', self.file_message.text)
        download = aria2.add_torrent(f'/app/data/{info_hash}.torrent', options={'select-file': ",".join(map(str, files))})

        # Wait for download complete
        self._set_state(TaskState.WORKING,
                        description=
                        f"{emoji.HOURGLASS_DONE} Download torrent"
        )
        self.reset_stats()
            
        while not download.is_complete and not download.status != "error":
            await asyncio.sleep(3)
            download.update()
            self._make_progress(download.completed_length, 
                                download.total_length, 
                                speed=download.download_speed,
                                eta=download.eta.seconds)

        self._set_state(TaskState.WAITING, description=f"{emoji.HOURGLASS_DONE} Files successfull downloaded")

        if download.status != 'complete':
            raise Exception(download.error_message)
        

        async with DavClient(hostname=self.webdav_hostname,
                            login=self.webdav_username,
                            password=self.webdav_password,
                            timeout=self.timeout,
                            chunk_size=2097152) as dav:
            for file in download.files:
                if file.is_metadata or not file.selected:
                    continue
                    
                async with aiofiles.open(file.path, 'rb') as f:
                    await self.upload_file(dav, f, file.length)
                os.unlink(file.path) # Delete file

        return None
