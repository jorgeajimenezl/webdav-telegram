import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import Client, emoji, filters
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from async_executor.executor import TaskExecutor
from async_executor.task import Task, TaskState
from button import ButtonFactory
from context import UserContext
from database import Database
from filesize import naturalsize
from module import Module
from modules.service import Service

# Services
from services.http import HttpService
from services.telegram import TelegramService

# from services.torrent import TorrentService


class WebdavModule(Module):
    SERVICES = [
        # TorrentService,
        TelegramService,
        HttpService,
    ]

    def __init__(
        self, context: UserContext, database: Database, scheduler: AsyncIOScheduler
    ) -> None:
        super().__init__(context, database)

        self.scheduler = scheduler
        self.app = None

        self.tasks_id = dict()
        self.executor = TaskExecutor()
        self.tasks = dict()
        self.tasks_lock = asyncio.Lock()
        self.factory = ButtonFactory()

        # Buttons
        self.cancel_group = self.factory.create_group("cancel")

    async def _on_task_end(self, task: Service):
        user = task.user
        state, description = task.state()

        if state == TaskState.ERROR or state == TaskState.CANCELED:
            await self.app.send_message(
                user, description, reply_to_message_id=task.file_message.message_id
            )

        if state == TaskState.SUCCESSFULL:
            await self.app.send_message(
                user,
                f"{emoji.CHECK_MARK_BUTTON} Successfull",
                reply_to_message_id=task.file_message.message_id,
            )

        async with self.tasks_lock:
            message = self.tasks.pop(task)
            self.tasks_id.pop(task.id)

            # Remove progress message
            try:
                if message != None:
                    await message.delete(True)
            except Exception:
                pass

    async def cancel_upload(self, app: Client, callback_query: CallbackQuery):
        await callback_query.answer("Scheduled stop")
        id = self.factory.get_value(callback_query.data)
        assert isinstance(id, int)

        async with self.tasks_lock:
            if id in self.tasks_id:
                self.tasks_id[id].cancel()

    async def upload_file(self, app: Client, message: Message):
        user = message.from_user.id
        cls = None

        for service in WebdavModule.SERVICES:
            if service.check(message):
                cls = service
                break

        if cls == None:
            await app.send_message(
                user, f"{emoji.CROSS_MARK} This action don't match with any service"
            )
            return

        data = self.database.get_data(user)

        # upload
        task = self.executor.add(
            cls,
            on_end_callback=self._on_task_end,
            user=user,
            file_message=message,
            pyrogram=app,
            split_size=int(data["split_size"]),
            hostname=data["server"],
            username=data["user"],
            password=data["password"],
            path=data["upload_path"],
        )

        async with self.tasks_lock:
            self.tasks[task] = await app.send_message(
                user,
                f"Waiting to process this action (Task #{task.id})",
                reply_markup=InlineKeyboardMarkup(
                    [[self.cancel_group.add(task.id, cachable=True).button("Cancel")]]
                ),
            )

            self.tasks_id[task.id] = task

    async def _updater(self):
        async with self.tasks_lock:
            for task, message in self.tasks.items():
                state, description = task.state()

                if state == TaskState.ERROR or state == TaskState.SUCCESSFULL:
                    continue

                if description == None:
                    continue

                current, total = task.progress()
                if (current or total) != None:
                    text = f"{description} ({naturalsize(current, format='%.3f')}, {naturalsize(total, format='%.3f')})"
                else:
                    text = f"{description} (...)"

                if message.text != text:
                    message.text = text
                    await message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    self.cancel_group.add(
                                        task.id, cachable=True
                                    ).button("Cancel")
                                ]
                            ]
                        ),
                    )

    def register_app(self, app: Client):
        self.app = app

        # Add to scheduler updater function
        self.scheduler.add_job(self._updater, "interval", seconds=2, max_instances=1)

        handlers = [
            MessageHandler(self.upload_file),
            self.cancel_group.callback_handler(self.cancel_upload),
        ]

        for u in handlers:
            app.add_handler(u)
