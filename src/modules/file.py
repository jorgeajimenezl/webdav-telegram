import asyncio
import os
from typing import Callable, Dict
from urllib.parse import urlparse

from aiodav.client import Client as DavClient
from aiodav.exceptions import RemoteResourceNotFound
from pyrogram import Client, emoji, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

import dialogs
from context import CONTEXT, UserContext
from database import Database
from humanize import naturalsize
from module import Module
from button import ButtonFactory


class FileModule(Module):
    def __init__(self, context: UserContext, database: Database) -> None:
        super().__init__(context, database)
        self.factory = ButtonFactory()

        # Groups
        self.delete_group = self.factory.create_group("delete")

    async def list(self, app: Client, message: Message, edit_message=False):
        user = message.from_user.id
        data = self.database.get_data(user)
        cwd = "/"
        ret = urlparse(data["server-uri"])

        async with DavClient(
            hostname=data["server-uri"],
            login=data["username"],
            password=data["password"],
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

                def get_button_label(info: Dict[str, str]):
                    _, name = get_path(info["path"])
                    return f"{emoji.OPEN_FILE_FOLDER if info['isdir'] else emoji.PACKAGE} {name}"

                while True:
                    nodes = await dav.list(cwd, get_info=True)
                    node, message = await dialogs.selection(
                        app,
                        user,
                        options=nodes,
                        description="**Select your file**",
                        multi_selection=False,
                        name_selector=get_button_label,
                        delete=False,
                        message=(message if edit_message else None),
                    )

                    if node is None:
                        break

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
                await app.send_message(user, f"Error getting file list: {e}")

    async def delete_file(self, app: Client, callback_query: CallbackQuery):
        user = callback_query.from_user.id
        path = self.factory.get_value(callback_query.data)
        assert isinstance(path, str)

        name = os.path.basename(path)
        data = self.database.get_data(user)

        async with DavClient(
            hostname=data["server-uri"],
            login=data["username"],
            password=data["password"],
        ) as dav:
            try:
                await dav.unlink(path)

                # Notify and go back
                await callback_query.answer(f"The item **{name}** has been deleted")
                # Schedule this task
                asyncio.create_task(
                    self.list(app, callback_query.message, edit_message=True)
                )
            except RemoteResourceNotFound:
                await app.send_message(
                    user, f"Resource **{path}** isn't longer available"
                )
            except Exception as e:
                await app.send_message(
                    user, f"Unexpected error while delete **{path}**: {e}"
                )

    async def free(self, app: Client, message: Message):
        user = message.from_user.id
        data = self.database.get_data(user)

        async with DavClient(
            hostname=data["server-uri"],
            login=data["username"],
            password=data["password"],
        ) as dav:
            try:
                n = await dav.free()
                await app.send_message(
                    user,
                    f"{emoji.BAR_CHART} Free: **{naturalsize(n, binary=True, format='%.3f')}**",
                )
            except Exception as e:
                await app.send_message(user, f"Unable to get free space: {e}")

    async def wipe(self, app: Client, message: Message):
        user = message.from_user.id
        data = self.database.get_data(user)

        answer = await dialogs.selection(
            app,
            user,
            ["Yes", "No"],
            "Confirm to delete all the files",
            multi_selection=False,
            cancellable=False,
        )

        if answer == "Yes":
            async with DavClient(
                hostname=data["server-uri"],
                login=data["username"],
                password=data["password"],
            ) as dav:
                try:

                    nodes = await dav.list()
                    for node in nodes:
                        await dav.unlink(node)
                    await app.send_message(
                        user, "All the files has been deleted successfully"
                    )
                except Exception as e:
                    await app.send_message(user, f"Unable to wipe the files: {e}")
        else:
            await app.send_message(user, "Wipe cancelled")

    def register(self, app: Client):
        def coro_wrapper(func: Callable[[Client, Message], None], **kwargs):
            async def wrapper(app: Client, event: Message):
                asyncio.create_task(func(app, event, **kwargs))

            return wrapper

        handlers = [
            MessageHandler(coro_wrapper(self.list), filters.command("list")),
            MessageHandler(self.free, filters.command("free")),
            MessageHandler(coro_wrapper(self.wipe), filters.command("wipe")),
            self.delete_group.callback_handler(self.delete_file),
        ]

        for u in handlers:
            app.add_handler(u)
