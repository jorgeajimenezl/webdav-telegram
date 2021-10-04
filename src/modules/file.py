import asyncio
import os
import traceback
from typing import Dict
from urllib.parse import urlparse

from aiodav.client import Client as DavClient
from aiodav.exceptions import RemoteResourceNotFound
from pyrogram import Client, emoji, filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import utils
from context import CONTEXT, UserContext
from database import Database
from filesize import naturalsize
from module import Module
from button import ButtonFactory


class FileModule(Module):
    def __init__(self, context: UserContext, database: Database) -> None:
        super().__init__(context, database)
        self.factory = ButtonFactory()

        # Groups
        self.delete_group = self.factory.create_group("delete")

    async def _list(self, app: Client, event: Message):
        # TODO: Fix this async bug
        asyncio.create_task(self.list(event.from_user.id, app))

    async def list(self, user: int, app: Client, message: Message = None):
        data = self.database.get_data(user)
        cwd = "/"
        ret = urlparse(data["server"])

        async with DavClient(
            hostname=data["server"], login=data["user"], password=data["password"]
        ) as dav:
            try:

                def get_path(path):
                    prefix = os.path.commonprefix((ret.path, path))
                    partial = (
                        path[len(prefix) :].rstrip("/")
                        if len(prefix) > 1
                        else path.rstrip("/")
                    )
                    name = os.path.basename(partial) if partial != cwd else ".."
                    if partial == cwd:
                        partial = os.path.dirname(partial)

                    return partial, name

                def create_button(info: Dict[str, str]):
                    _, name = get_path(info["path"])
                    return f"{emoji.OPEN_FILE_FOLDER if info['isdir'] else emoji.PACKAGE} {name}"

                while True:
                    nodes = await dav.list(cwd, get_info=True)
                    node, message = await utils.selection(
                        app,
                        user,
                        options=nodes,
                        message_text="**Select your file**",
                        multi_selection=False,
                        name_selector=create_button,
                        delete=False,
                        message=message,
                    )

                    if node == None:
                        break

                    node = node[0]
                    cwd, _ = get_path(node["path"])

                    if not node["isdir"]:
                        await message.edit_text(
                            f"Name: {os.path.basename(cwd)}\n"
                            f"Created: {node['created']}\n"
                            f"Size: {naturalsize(node['size'], binary=True)}\n"
                            f"Modified: {node['modified']}\n"
                            f"Etag: {node['etag']}",
                            reply_markup=InlineKeyboardMarkup(
                                [
                                    [
                                        InlineKeyboardButton(
                                            f"{emoji.DOWN_ARROW} Download",
                                            callback_data=b"1",
                                        ),
                                        InlineKeyboardButton(
                                            f"{emoji.PENCIL} Rename", callback_data=b"1"
                                        ),
                                        self.delete_group.add(
                                            cwd, cachable=True
                                        ).button(f"{emoji.CROSS_MARK} Delete"),
                                    ]
                                ]
                            ),
                        )

                        break
            except Exception as e:
                # print("Error: " + str(e))
                await app.send_message(user, f"Error getting file list: {e}")

    async def _delete_file(self, app: Client, callback_query: CallbackQuery):
        user = callback_query.from_user.id
        path = self.factory.get_value(callback_query.data)
        assert isinstance(path, str)

        name = os.path.basename(path)
        data = self.database.get_data(user)

        async with DavClient(
            hostname=data["server"], login=data["user"], password=data["password"]
        ) as dav:
            try:
                await dav.unlink(path)

                # Notify and go back
                await callback_query.answer(f"The item **{name}** has been deleted")
                asyncio.create_task(self.list(user, app, callback_query.message))
                return
            except RemoteResourceNotFound:
                await app.send_message(
                    user, f"Resource **{path}** isn't longer available"
                )
            except Exception:
                await app.send_message(
                    user, f"Unexpected error while delete **{path}**"
                )

    async def free(self, app: Client, message: Message):
        user = message.from_user.id
        data = self.database.get_data(user)

        async with DavClient(
            hostname=data["server"], login=data["user"], password=data["password"]
        ) as dav:
            try:
                n = await dav.free()
                await app.send_message(
                    user,
                    f"{emoji.BAR_CHART} Free: **{naturalsize(n, binary=True, format='%.3f')}**",
                )
            except Exception:
                await app.send_message(user, "Unable to get free space")

    def register_app(self, app: Client):
        handlers = [
            MessageHandler(self._list, filters.command("list") & filters.private),
            MessageHandler(self.free, filters.command("free") & filters.private),
            self.delete_group.callback_handler(self._delete_file),
        ]

        for u in handlers:
            app.add_handler(u)
