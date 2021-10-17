import re

from pyrogram import Client, emoji, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message, ReplyKeyboardMarkup, ReplyKeyboardRemove

from context import CONTEXT, UserContext
from database import Database
from module import Module


class SettingsModule(Module):
    COMMAND_NAME = "settings"
    # Text, Description, Regex, Field name, Converter
    # yapf: disable
    MENU = {
        f"{emoji.GLOBE_WITH_MERIDIANS} Server": ("Write the hostname", r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)", 'server', None),
        f"{emoji.BUST_IN_SILHOUETTE} Username": ("Write the username", r"\S+", 'user', None),
        f"{emoji.KEY} Password": ("Write the password", r".+", 'password', None),
        f"{emoji.STRAIGHT_RULER} Split Size": ("Write the split size (max file size for split (Default: 100MB))", r"\d+", 'split_size', lambda x: int(x)),
        f"Upload Path": ("Write the upload files path", r"[\S/]+", "upload_path", None),
        f"{emoji.UPWARDS_BUTTON} Streaming": ("Turn on for stream directly from service to webdav", r"(on|off)", "streaming", None),
    }
    # yapf: enable

    def __init__(self, context: UserContext, database: Database) -> None:
        super().__init__(context, database)

    async def _settings(self, app: Client, message: Message):
        user = message.from_user.id

        if not self.database.contains_user(user):
            await app.send_message(user, "Must be registred. **Write /start**")
            return

        self.context.update(user, CONTEXT["SETTINGS"])
        await app.send_message(
            user,
            "Select action:",
            reply_markup=ReplyKeyboardMarkup(
                [[name] for name in SettingsModule.MENU.keys()] + [["Back"]]
            ),
        )

    async def _setting_menu(self, app: Client, message: Message):
        user = message.from_user.id

        if message.text.lower() == "back":
            self.context.update(user, CONTEXT["IDLE"])
            await app.send_message(user, "Home", reply_markup=ReplyKeyboardRemove())
            return

        if not message.text in SettingsModule.MENU:
            await app.send_message(user, "Unknow option. Select **valid** action")
            return

        description, *_ = SettingsModule.MENU[message.text]
        self.context.update(user, CONTEXT[message.text])

        await app.send_message(
            user,
            f"{description}",
            reply_markup=ReplyKeyboardRemove(),
            disable_web_page_preview=True,
        )

    async def _setting_handler_menu(self, app: Client, message: Message):
        user = message.from_user.id

        context = self.context.resolve(user)
        id = self.ids[context]
        _, pattern, field, converter = SettingsModule.MENU[id]

        if re.fullmatch(pattern, message.text):
            payload = {field: converter(message.text) if converter else message.text}
            self.database.set_data(user, **payload)
            await app.send_message(
                user, f"{emoji.CHECK_MARK_BUTTON} {id} successfull updated"
            )
        else:
            await app.send_message(user, f"{emoji.CROSS_MARK} Invalid value")

        await self._settings(app, message)

    def register_app(self, app: Client):
        l = len(CONTEXT)

        self.ids = {}
        for i, x in enumerate(SettingsModule.MENU.keys()):
            CONTEXT[x] = 1 << (l + i)
            self.ids[1 << (l + i)] = x

        mask = ((1 << len(SettingsModule.MENU)) - 1) << l

        handlers = [
            MessageHandler(
                self._settings, filters.command(SettingsModule.COMMAND_NAME)
            ),
            MessageHandler(
                self._setting_menu,
                filters.text & self.context.filter(CONTEXT["SETTINGS"]),
            ),
            MessageHandler(
                self._setting_handler_menu, filters.text & self.context.filter(mask)
            ),
        ]

        for u in handlers:
            app.add_handler(u)
