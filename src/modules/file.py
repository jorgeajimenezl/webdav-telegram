from module import Module
from pyrogram import Client, emoji, filters
from urllib.parse import urlparse

from pyrogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                            Message, CallbackQuery)
from pyrogram.handlers import MessageHandler, CallbackQueryHandler

import os, traceback
from aiodav.client import Client as DavClient
from aiodav.exceptions import RemoteResourceNotFound
from filesize import naturalsize
from context import CONTEXT, UserContext
from database import Database


class FileModule(Module):
    def __init__(self, context: UserContext, database: Database) -> None:
        super().__init__(context, database)

    async def list(self, app: Client, event: Message):
        user = event.from_user.id

        data = self.database.get_data(user)
        cwd = data['cwd']
        ret = urlparse(data['server'])

        async with DavClient(hostname=data['server'],
                             login=data['user'],
                             password=data['password']) as dav:
            try:
                nodes = await dav.list(cwd, get_info=True)

                def create_button(info: str):
                    prefix = os.path.commonprefix((ret.path, info['path']))
                    partial = info['path'][len(prefix):].rstrip(
                        '/') if len(prefix) > 1 else info['path'].rstrip('/')
                    name = os.path.basename(
                        partial) if partial != cwd else '..'
                    if partial == cwd:
                        partial = os.path.dirname(partial)

                    return [
                        InlineKeyboardButton(
                            f"{emoji.OPEN_FILE_FOLDER if info['isdir'] else ''} {name}",
                            callback_data=
                            f"{'cd' if info['isdir'] else 'open'} {partial}")
                    ]

                await app.send_message(
                    user,
                    f"{emoji.LIGHT_BULB} {cwd if cwd != '' else '/'}",
                    reply_markup=InlineKeyboardMarkup(
                        [create_button(node) for node in nodes]))
            except Exception as e:
                # print("Error: " + str(e))
                self.database.set_data(user, cwd="/")

                await app.send_message(
                    user,
                    f"Error while get current directory information. **Going to the root.**"
                )

    async def _file_info(self, app: Client, callback_query: CallbackQuery):
        user = callback_query.from_user.id

        data = self.database.get_data(user)
        _, _, path = callback_query.data.partition(' ')

        async with DavClient(hostname=data['server'],
                             login=data['user'],
                             password=data['password']) as dav:
            try:
                info = await dav.info(path)
                name = os.path.basename(path)

                await app.send_message(
                    user, f"Name: {name}\n"
                    f"Created: {info['created']}\n"
                    f"Size: {naturalsize(info['size'])}\n"
                    f"Modified: {info['modified']}\n"
                    f"Etag: {info['etag']}",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(f'{emoji.DOWN_ARROW} Download',
                                             callback_data=f"download {path}"),
                        InlineKeyboardButton(f'{emoji.PENCIL} Rename',
                                             callback_data=f"rename {path}"),
                        InlineKeyboardButton(f'{emoji.CROSS_MARK} Delete',
                                             callback_data=f"delete {path}")
                    ]]))
            except RemoteResourceNotFound:
                await app.send_message(
                    user, f"Resource **{path}** isn't longer available")

    async def _change_directory(self, app: Client,
                                callback_query: CallbackQuery):
        user = callback_query.from_user.id

        _, _, path = callback_query.data.partition(' ')
        data = self.database.get_data(user)

        async with DavClient(hostname=data['server'],
                             login=data['user'],
                             password=data['password']) as dav:
            try:
                if (await dav.exists(path)):
                    self.database.set_data(user, cwd=path)
                    await app.send_message(
                        user,
                        f"Current working directory has been changed to **{path}**"
                    )
                    await self.list(app, callback_query)

            except RemoteResourceNotFound:
                await app.send_message(
                    user, f"Directory **{path}** isn't longer available")

    async def _delete_file(self, app: Client, callback_query: CallbackQuery):
        user = callback_query.from_user.id

        _, _, path = callback_query.data.partition(' ')
        name = os.path.basename(path)
        data = self.database.get_data(user)

        async with DavClient(hostname=data['server'],
                             login=data['user'],
                             password=data['password']) as dav:
            try:
                await dav.unlink(path)
                await app.send_message(
                    user, f"The item **{name}** has been deleted")
            except RemoteResourceNotFound:
                await app.send_message(
                    user, f"Resource **{path}** isn't longer available")
            except Exception:
                await app.send_message(
                    user, f"Unexpected error while delete **{path}**")

    async def select_directory(self, app: Client,
                               callback_query: CallbackQuery):
        user = callback_query.from_user.id
        data = self.database.get_data(user)

        if isinstance(callback_query, CallbackQuery):
            _, _, path = callback_query.data.partition(' ')
        else:
            path = data['cwd']

        ret = urlparse(data['server'])
        async with DavClient(hostname=data['server'],
                             login=data['user'],
                             password=data['password']) as dav:
            try:
                nodes = await dav.list(path, get_info=True)

                def create_button(info: str):
                    prefix = os.path.commonprefix((ret.path, info['path']))
                    partial = info['path'][len(prefix):].rstrip(
                        '/') if len(prefix) > 1 else info['path'].rstrip('/')
                    name = os.path.basename(
                        partial) if partial != path else '..'
                    if partial == path:
                        partial = os.path.dirname(partial)

                    return [
                        InlineKeyboardButton(
                            f"{emoji.OPEN_FILE_FOLDER} {name}",
                            callback_data=f"select {partial}")
                    ]

                if isinstance(callback_query, CallbackQuery):
                    await callback_query.edit_message_reply_markup(
                        InlineKeyboardMarkup([
                            create_button(node)
                            for node in nodes if node['isdir']
                        ] + [[
                            InlineKeyboardButton(
                                f'{emoji.CHECK_MARK_BUTTON} SELECT',
                                callback_data=f'done {path}')
                        ]]))
                else:
                    await app.send_message(
                        user,
                        f"{emoji.LIGHT_BULB} **Select destination:** {path if path != '' else '/'}",
                        parse_mode='markdown',
                        reply_markup=InlineKeyboardMarkup([
                            create_button(node)
                            for node in nodes if node['isdir']
                        ] + [[
                            InlineKeyboardButton(
                                f'{emoji.CHECK_MARK_BUTTON} SELECT',
                                callback_data=f'done {path}')
                        ]]))
            except Exception as e:
                await app.send_message(
                    user,
                    f"Error while get current directory information. **Going to the root.**",
                    parse_mode='markdown')
                tb = traceback.format_exc()
                await app.send_message(user, f"Error: {tb}")

                # Cancel selection
                if isinstance(callback_query, CallbackQuery):
                    await callback_query.message.delete(True)
                else:
                    await callback_query.delete(True)

                self.context.update(user, CONTEXT['IDLE'])

    async def free(self, app: Client, message: Message):
        user = message.from_user.id
        data = self.database.get_data(user)

        async with DavClient(hostname=data['server'],
                             login=data['user'],
                             password=data['password']) as dav:
            try:
                n = await dav.free()
                await app.send_message(user, f"{emoji.BAR_CHART} Free: **{naturalsize(n, format='%.3f')}**")
            except Exception:
                await app.send_message(user, "Unable to get free space")

    def register_app(self, app: Client):
        handlers = [
            MessageHandler(self.list,
                           filters.command("list") & filters.private),
            MessageHandler(self.free,
                           filters.command("free") & filters.private),
            CallbackQueryHandler(self._file_info,
                                 ~filters.bot & filters.regex('^open .+$')),
            CallbackQueryHandler(self._change_directory,
                                 ~filters.bot & filters.regex('^cd .+$')),
            CallbackQueryHandler(self._delete_file,
                                 ~filters.bot & filters.regex('^delete .+$')),
            CallbackQueryHandler(self.select_directory,
                                 ~filters.bot & filters.regex('^select .+$'))
        ]

        for u in handlers:
            app.add_handler(u)
