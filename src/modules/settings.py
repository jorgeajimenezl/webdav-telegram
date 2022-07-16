import re
from typing import Callable, Coroutine, Dict

from pyrogram import Client, emoji, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    CallbackQuery,
    InlineKeyboardButton,
)
from button import ActionButton, ButtonFactory

from context import CONTEXT, UserContext
from database import Database
from module import Module
import utils


class SettingsModule(Module):
    COMMAND_NAME = "settings"
    # Text, Description, Regex, Field name, Converter
    MENU = {
        "server-uri": (
            f"{emoji.GLOBE_WITH_MERIDIANS} Server",
            "Write the hostname",
            r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)",
            str,
        ),
        "username": (
            f"{emoji.BUST_IN_SILHOUETTE} Username",
            "Write the username",
            r"\S+",
            str,
        ),
        "password": (
            f"{emoji.KEY} Password",
            "Write the password",
            r".+",
            str,
        ),
        "split-size": (
            f"{emoji.STRAIGHT_RULER} Split Size",
            "Write the split size (max file size for split (Default: 100MB))",
            r"\d+",
            int,
        ),
        "upload-path": (
            f"{emoji.FLOPPY_DISK} Upload Path",
            "Write the upload files path",
            r"[\S\/]+",
            str,
        ),
        "streaming": (
            f"{emoji.UPWARDS_BUTTON} Streaming",
            "Turn on for stream directly from service to webdav (Default: False)",
            r"(on|off|true|false)",
            bool,
        ),
        "use-libcurl": (
            f"{emoji.HAMBURGER} Libcurl",
            "Use curl instead default python requests library (Default: False). **WARNING: This option don't support streaming or parallel downloads, are mutually exclued**",
            r"(on|off|true|false)",
            bool,
        ),
        "upload-parallel": (
            f"{emoji.UPWARDS_BUTTON} Parallel",
            "Turn on for upload parallely the pieces splied from the file (Default: False)",
            r"(on|off|true|false)",
            bool,
        ),
        "checksum": (
            f"{emoji.UPWARDS_BUTTON} Checksum",
            "Turn on for perform a checksum of the uploaded files (Default: True)",
            r"(on|off|true|false)",
            bool,
        ),
        # "use-compression": (
        #     f"{emoji.CARD_FILE_BOX} Compress",
        #     "Turn on for compress all files with tar.zstd format (Default: False)",
        #     r"(on|off|true|false)",
        #     bool,
        # ),
        "file-password": (
            f"{emoji.KEYCAP_ASTERISK} File Password",
            "Write the password to encrypt all files (Default: Empty)",
            r".*",
            str,
        ),
    }

    def __init__(self, context: UserContext, database: Database) -> None:
        super().__init__(context, database)
        self.factory = ButtonFactory()
        self.buttons: Dict[str, ActionButton] = dict()
        self.close_action = self.factory.create_action("close-action")
        self.handlers = []

    def _get_button(self, user: int, id: str) -> InlineKeyboardButton:
        name, _, _, cls = SettingsModule.MENU[id]

        if issubclass(cls, bool):
            data = self.database.get_data(user)
            v = utils.get_bool(data.get(id, False))
            return self.buttons[id].button(
                f"[{emoji.CHECK_MARK_BUTTON if v else emoji.CROSS_MARK}] {name}"
            )
        return self.buttons[id].button(name)

    def _get_keyboard(self, user: int):
        return InlineKeyboardMarkup(
            [
                [
                    self._get_button(user, "server-uri"),
                    self._get_button(user, "upload-path"),
                ],
                [
                    self._get_button(user, "username"),
                    self._get_button(user, "password"),
                ],
                [
                    self._get_button(user, "split-size"),
                    self._get_button(user, "upload-parallel"),
                ],
                [
                    self._get_button(user, "streaming"),
                    self._get_button(user, "use-libcurl"),
                ],
                [
                    # self._get_button(user, "use-compression"),
                    self._get_button(user, "checksum"),
                    self._get_button(user, "file-password"),
                ],
                [self.close_action.button(f"{emoji.LEFT_ARROW} Close")],
            ]
        )

    async def settings(self, app: Client, message: Message):
        user = message.from_user.id

        if not self.database.contains_user(user):
            await app.send_message(user, "Must be registred. **Write /start**")
            return

        self.context.update(user, CONTEXT["SETTINGS"])
        return await app.send_message(
            user,
            "Settings:",
            reply_markup=self._get_keyboard(user),
        )

    async def settings_handler_menu(self, app: Client, message: Message):
        user = message.from_user.id
        id = self.database.get_data(user)["settings_context"]
        text, _, pattern, converter = SettingsModule.MENU[id]

        if re.fullmatch(pattern, message.text):
            payload = {id: converter(message.text) if converter else message.text}
            self.database.set_data(user, **payload)
            await app.send_message(
                user, f"{emoji.CHECK_MARK_BUTTON} {text} successfull updated"
            )
        else:
            await app.send_message(user, f"{emoji.CROSS_MARK} Invalid value")

        await self.settings(app, message)

    async def settings_menu(self, app: Client, callback_query: CallbackQuery):
        user = callback_query.from_user.id

        id = self.factory.get_value(callback_query.data)
        _, description, _, cls = SettingsModule.MENU[id]

        if not issubclass(cls, bool):
            self.database.set_data(user, settings_context=id)
            self.context.update(user, CONTEXT["SETTINGS_EDIT"])

            await callback_query.message.delete(True)
            await app.send_message(
                user,
                f"{description}",
                disable_web_page_preview=True,
            )
        else:
            data = self.database.get_data(user)
            v = utils.get_bool(data.get(id, False))
            payload = {id: str((not v))}
            self.database.set_data(user, **payload)

            await callback_query.edit_message_reply_markup(self._get_keyboard(user))
            await callback_query.answer(f"Set value to {not v}")

    async def close(self, app: Client, callback_query: CallbackQuery):
        user = callback_query.from_user.id
        self.context.update(user, CONTEXT["IDLE"])
        await callback_query.message.delete(True)

    def register(self, app: Client):
        handlers = [
            MessageHandler(self.settings, filters.command(SettingsModule.COMMAND_NAME)),
            MessageHandler(
                self.settings_handler_menu,
                filters.text & self.context.filter(CONTEXT["SETTINGS_EDIT"]),
            ),
            self.close_action.callback_handler(self.close),
        ]

        for k in SettingsModule.MENU.keys():
            self.buttons[k] = self.factory.create_action(k)
            handlers.append(self.buttons[k].callback_handler(self.settings_menu))

        for u in handlers:
            app.add_handler(u)
