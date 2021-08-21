import uvloop

from modules.webdav import WebdavModule

uvloop.install()

from pyrogram import (filters, emoji, idle)
from pyrogram import Client as PyrogramClient
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import asyncio, yaml, re

from context import CONTEXT, UserContext
from database import Database

from filesize import naturalsize

from executor import TaskExecutor
from task import Task, TaskState

# Modules
from modules.settings import SettingsModule
from modules.file import FileModule

# Tasks
from tasks.telegram_to_webdav import TelegramToWebdav

DATA_FOLDER_PATH = './data/'
DOWNLOAD_CHUNK_SIZE = 2097152  # 2 MB

# Read config file
with open('config.yml', 'r') as file:
    CONFIG = yaml.load(file.read(), Loader=yaml.Loader)

database = Database(db=0, config=CONFIG)
context = UserContext(db=0, config=CONFIG)
executor = TaskExecutor()
tasks = dict()
tasks_lock = asyncio.Lock()

# Modules instantiation
settings_module = SettingsModule(context, database)
file_module = FileModule(context, database)
webdav_moduele = WebdavModule(context, database, executor, tasks, tasks_lock)

app = PyrogramClient('deverlop',
                     api_id=CONFIG['telegram']['api-id'],
                     api_hash=CONFIG['telegram']['api-hash'],
                     bot_token=CONFIG['telegram']['bot-token'])

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


async def updater():
    async with tasks_lock:
        for task, message in tasks.items():
            state, description = task.state()

            if state == TaskState.ERROR or \
                state == TaskState.SUCCESSFULL:
                continue

            if description == None:
                continue

            current, total = task.progress()

            text = f"{description} ({naturalsize(current, format='%.3f')}, {naturalsize(total, format='%.3f')})"
            if message.text != text:
                message.text = text
                await message.edit_text(text)


async def main():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(updater, "interval", seconds=2, max_instances=1)

    async with app:
        scheduler.start()

        # Set Bot Commands
        await app.set_bot_commands([
            BotCommand("start", f"{emoji.ROBOT} Start the bot"),
            BotCommand("settings", f"{emoji.GEAR} Bot settings"),
            BotCommand("list", f"{emoji.OPEN_FILE_FOLDER} List cloud entries")
        ])
        await idle()


if __name__ == "__main__":
    app.run(main())
