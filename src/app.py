import uvloop

uvloop.install()

import asyncio
import os
import re

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import Client as PyrogramClient
from pyrogram import emoji, filters, idle
from pyrogram.types import (BotCommand, InlineKeyboardButton,
                            InlineKeyboardMarkup, Message)

from context import CONTEXT, UserContext
from database import Database
from filesize import naturalsize
from modules.file import FileModule
# Modules
from modules.settings import SettingsModule
from modules.webdav import WebdavModule

DATA_FOLDER_PATH = './data/'
DOWNLOAD_CHUNK_SIZE = 2097152  # 2 MB

# Read config file
with open('config.yml', 'r') as file:
    CONFIG = yaml.load(file.read(), Loader=yaml.Loader)
    
    CONFIG['telegram']['api-id'] = os.getenv('TELEGRAM_API_ID') or CONFIG['telegram']['api-id']
    CONFIG['telegram']['api-hash'] = os.getenv('TELEGRAM_API_HASH') or CONFIG['telegram']['api-hash']
    CONFIG['telegram']['bot-token'] = os.getenv('TELEGRAM_BOT_TOKEN') or CONFIG['telegram']['bot-token']
    CONFIG['redis']['host'] = os.getenv('REDIS_HOST') or CONFIG['redis']['host']


scheduler = AsyncIOScheduler()
database = Database(db=0, config=CONFIG)
context = UserContext(db=0, config=CONFIG)

# Modules instantiation
settings_module = SettingsModule(context, database)
file_module = FileModule(context, database)
webdav_moduele = WebdavModule(context, database, scheduler)

# WARNING: workers parameter pushed because that will run in a 1-CPU
app = PyrogramClient('deverlop',
                     api_id=CONFIG['telegram']['api-id'],
                     api_hash=CONFIG['telegram']['api-hash'],
                     bot_token=CONFIG['telegram']['bot-token'],
                     workers=5)

# Register all modules callbacks
settings_module.register_app(app)
file_module.register_app(app)
webdav_moduele.register_app(app)


@app.on_message(filters.command("start") & filters.private)
async def start(_, message: Message):
    user = message.from_user.id
    context.update(user, CONTEXT['INITIALIZE'])

    if not database.contains_user(user):
        database.add_user(user)
        name = message.from_user.first_name or message.from_user.username

        await app.send_message(user,
                               f"Welcome **{name}**.",
                               parse_mode="markdown")
        await app.send_message(
            user, f"To start to use put your configuration in /settings")

        context.update(user, CONTEXT['IDLE'])
    else:
        await app.send_message(user, "You are already logged")


async def main():
    async with app:
        scheduler.start()

        # TODO: Wait to fix bug
        # Set Bot Commands
        # await app.set_bot_commands([
        #     BotCommand("start", f"{emoji.ROBOT} Start the bot"),
        #     BotCommand("settings", f"{emoji.GEAR} Bot settings"),
        #     BotCommand("list", f"{emoji.OPEN_FILE_FOLDER} List cloud entries"),
        #     BotCommand("free", f"{emoji.BAR_CHART} Free space on cloud"),
        # ])
        await idle()


if __name__ == "__main__":
    app.run(main())
