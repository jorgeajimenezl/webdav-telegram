import asyncio
import imp
from services.youtube import YoutubeService
import utils
from typing import List, Type

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pyrogram import Client, emoji, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)

from async_executor.executor import TaskExecutor
from async_executor.task import Task, TaskState
from button import ButtonFactory
from context import CONTEXT, UserContext
from database import Database
from humanize import naturalsize, naturaldelta
from module import Module
from modules.service import Service

# Services
from services.http import HttpService
from services.telegram import TelegramService
from services.torrent import TorrentService
from services.mega import MegaService


class WebdavModule(Module):
    SERVICES: List[Service] = [
        TorrentService,
        TelegramService,
        MegaService,
        YoutubeService,
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

    # async def _on_task_precall(self, task: Service):
    #     if hasattr(task, 'options'):
    #         await task.options()

    async def _on_task_end(self, task: Service):
        user = task.user
        state, description = task.state()

        if state == TaskState.ERROR or state == TaskState.CANCELED:
            for piece in utils.cut(description, 4096):
                await self.app.send_message(
                    user, piece, reply_to_message_id=task.file_message.id
                )

        if state == TaskState.SUCCESSFULL:
            await self.app.send_message(
                user,
                f"{emoji.CHECK_MARK_BUTTON} Successfull",
                reply_to_message_id=task.file_message.id,
            )

            if task.checksum and len(task.sums) > 0:
                piece = "\n".join([f"**{n}**: `{c}`\n" for n, c in task.sums.items()])
                await self.app.send_message(
                    user,
                    f"{emoji.INBOX_TRAY} Checksums (SHA1):\n\n{piece}",
                    reply_to_message_id=task.file_message.id,
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

        await self.push_task(app, user, cls, message)

    async def push_task(
        self, app: Client, user: int, cls: Type, message: Message, **kwargs
    ):
        data = self.database.get_data(user)

        # Add the task to the executor
        task = self.executor.add(
            cls,
            on_end_callback=self._on_task_end,
            user=user,
            file_message=message,
            pyrogram=app,
            split_size=int(data["split-size"]),
            streaming=utils.get_bool(data["streaming"]),
            parallel=utils.get_bool(data["upload-parallel"]),
            checksum=utils.get_bool(data["checksum"]),
            hostname=data["server-uri"],
            username=data["username"],
            password=data["password"],
            path=data["upload-path"],
            push_task_method=self.push_task,  # To allow the services push anothers services call
            **kwargs,
        )

        if task == None:
            await app.send_message(user, f"{emoji.CROSS_MARK} Unable to start task")
            return

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
                    current_text = (
                        naturalsize(current, binary=True, format="%.3f")
                        if current != None
                        else "Unknown"
                    )
                    total_text = (
                        naturalsize(total, binary=True, format="%.3f")
                        if total != None
                        else "Unknown"
                    )

                    speed = task.speed()
                    eta = task.eta()

                    speed_text = (
                        utils.get_str(naturalsize(speed, binary=True))
                        if speed != None
                        else "Unknown"
                    )
                    eta_text = (
                        utils.get_str(naturaldelta(eta)) if eta != None else "Unknown"
                    )

                    text = f"{description} ({current_text} / {total_text})\nSpeed: {speed_text}/sec\nETA: {eta_text}"
                else:
                    text = f"{description}"

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

    # async def urls_batch(self, app: Client, message: Message):
    #     user = message.from_user.id
    #     self.context.update(user, CONTEXT["URLS_BATCH"])

    #     await app.send_message(
    #         user,
    #         f"{emoji.CHECK_MARK_BUTTON} Please send me a list of URLs",
    #         reply_markup=InlineKeyboardMarkup(
    #             [
    #                 [
    #                     InlineKeyboardButton(
    #                         "Cancel",
    #                         callback_data=self.factory.create_data("cancel"),
    #                     )
    #                 ]
    #             ]
    #         ),
    #     )

    def register(self, app: Client):
        self.app = app

        # Add to scheduler updater function
        self.scheduler.add_job(self._updater, "interval", seconds=3, max_instances=1)

        handlers = [
            app.add_handler(MessageHandler(self.upload_file)),
            self.cancel_group.callback_handler(self.cancel_upload),
            # MessageHandler(self.urls_batch, filters.command("batch")),
        ]

        for u in handlers:
            app.add_handler(u)
