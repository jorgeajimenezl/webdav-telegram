import os
import sys

from pyrogram import Client, emoji, filters
from pyrogram.types import Message
from pyrogram.handlers import MessageHandler

from context import UserContext
from database import Database
from module import Module


class AdministratorModule(Module):
    def __init__(self, context: UserContext, database: Database) -> None:
        super().__init__(context, database)

    def restart(self):
        python = sys.executable
        os.execl(python, python, *sys.argv)

    async def restart_command(self, app: Client, message: Message):
        user = message.from_user.id

        if not self.database.is_admin(user):
            await app.send_message(
                user, f"{emoji.RED_CIRCLE} Only administrators can use this command."
            )
            return

        await app.send_message(user, "Restarting the application...")
        self.restart()

    def register(self, app: Client):
        app.add_handler(
            MessageHandler(
                self.restart_command,
                filters.command("restart"),
            )
        )
