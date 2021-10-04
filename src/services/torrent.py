import asyncio
import os
import re
import traceback
import aiofiles
from asyncio.exceptions import CancelledError

import aria2p
from aiodav.client import Client as DavClient

from pyrogram import emoji
from pyrogram.types import Message

import utils
from async_executor.task import TaskState
from modules.service import Service


class TorrentService(Service):
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
            rf'magnet:\?(&?((xt=urn:[a-z0-9]+:[\w\.]+)|(dn=[\w\+%-]+)|(xl=[^&]+)|(as=[^&]+)|(kt=[^&]+)|(xs=[^&]+)|(mt=[^&]+)|(tr=[^&]+)|(x=[^&]+)))*',
            m.text)

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


    async def options(self, aria2: aria2p.API) -> None:       
        d = aria2.add_magnet(self.file_message.text,
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

        hash = d.info_hash
        d = aria2.add_torrent(f'/app/torrent_data/{hash}.torrent',
                              options={'dry-run': 'true'})

        app = self.pyrogram
        files = await utils.selection(
            app,
            self.user,
            options=d.files,
            message_text='**Select files to download**',
            name_selector=lambda x: os.path.basename(x.path))

        return [p.index for p in files]

    async def start(self) -> None:
        aria2 = aria2p.API(
            aria2p.Client(host="http://localhost", port=6800, secret=""))

        try:
            # Chossing torrent files to download            
            files = await self.options(aria2)       

            self._set_state(TaskState.STARTING)    
            download = aria2.add_magnet(self.file_message.text, options={'select-file': ",".join(files)})

            # Wait for download complete
            self._set_state(TaskState.WORKING,
                            description=
                            f"{emoji.HOURGLASS_DONE} Download torrent"
                    )

            while not download.is_complete:
                await asyncio.sleep(5)
                download.update()
                self._make_progress(download.completed_length, download.total_length)

            if download.status == 'error':
                raise Exception(download.error_message)

            async with DavClient(hostname=self.webdav_hostname,
                                login=self.webdav_username,
                                password=self.webdav_password,
                                timeout=10 * 60 * 5,
                                chunk_size=1048576) as dav:
                for file in download.files:
                    if file.is_metadata or not file.selected:
                        continue

                    self._set_state(TaskState.WORKING,
                            description=
                            f"{emoji.HOURGLASS_DONE} Upload {os.path.basename(file.path)} to webdav server"
                    )

                    self.upload_file(file.path, file.length, dav)
                    os.unlink(file.path) # Delete file                   

                self._set_state(TaskState.SUCCESSFULL)                
        except CancelledError:
            self._set_state(TaskState.CANCELED, f"Task cancelled")
        except Exception as e:
            self._set_state(
                TaskState.ERROR,
                f"{emoji.CROSS_MARK} Error: {traceback.format_exc()}")

        return None
