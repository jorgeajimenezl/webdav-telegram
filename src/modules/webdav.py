import asyncio
from uuid import UUID
import utils
import psutil
from typing import Dict, List, Type

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
from services.git import GitService
from services.youtube import YoutubeService
from services.urlbatch import URLBatchService


class WebdavModule(Module):
    SERVICES: List[Service] = [
        URLBatchService,
        TorrentService,
        TelegramService,
        MegaService,
        YoutubeService,
        GitService,
        HttpService,
    ]

    def __init__(
        self, context: UserContext, database: Database, scheduler: AsyncIOScheduler
    ) -> None:
        super().__init__(context, database)

        self.scheduler = scheduler
        self.app = None

        self.tasks_id: Dict[UUID, Task] = dict()
        self.executor = TaskExecutor()
        self.tasks: Dict[Task, Message] = dict()
        self.tasks_lock = asyncio.Lock()
        self.factory = ButtonFactory()

        # Buttons
        self.cancel_group = self.factory.create_group("cancel")

    # async def _on_task_precall(self, task: Service):
    #     if hasattr(task, 'options'):
    #         await task.options()

    async def _on_task_end(self, task: Service):
        user = task.user
        state, description = task.state

        match state:
            case TaskState.ERROR | TaskState.CANCELLED:
                for piece in utils.cut(description, 4096):
                    await self.app.send_message(
                        user, piece, reply_to_message_id=task.file_message.id
                    )
            case TaskState.SUCCESSFULL:
                if task.checksum and len(task.sums) > 0:
                    checksums = "\n".join(
                        [
                            f"**{filename}**: `{checksum}`\n"
                            for filename, checksum in task.sums.items()
                        ]
                    )
                    await self.app.send_message(
                        user,
                        f"{emoji.CHECK_MARK_BUTTON} Successfull\n\n{emoji.INBOX_TRAY} Checksums (SHA1):\n\n{checksums}",
                        reply_to_message_id=task.file_message.id,
                    )
                else:
                    await self.app.send_message(
                        user,
                        f"{emoji.CHECK_MARK_BUTTON} Successfull",
                        reply_to_message_id=task.file_message.id,
                    )

        async with self.tasks_lock:
            message = self.tasks.pop(task)
            self.tasks_id.pop(task.id)

            # Remove progress message
            try:
                if message is not None:
                    await message.delete(True)
            except Exception:
                pass

    async def cancel_upload(self, app: Client, callback_query: CallbackQuery):
        await callback_query.answer("Scheduled stop", show_alert=True)
        id = self.factory.get_value(callback_query.data)
        assert isinstance(id, UUID)

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

        if cls is None:
            await app.send_message(
                user, f"{emoji.CROSS_MARK} This action don't match with any service"
            )
            return

        await self.push_task(app, user, cls, message)

    async def push_task(
        self, app: Client, user: int, cls: Type, message: Message, **kwargs
    ):
        data = self.database.get_data(user)

        # Instantiate task
        task: Task = cls(
            user=user,
            file_message=message,
            pyrogram=app,
            split_size=int(data["split-size"]),
            streaming=utils.get_bool(data["streaming"]),
            parallel=utils.get_bool(data["upload-parallel"]),
            checksum=utils.get_bool(data["checksum"]),
            overwrite=utils.get_bool(data["file-overwrite"]),
            hostname=data["server-uri"],
            username=data["username"],
            password=data["password"],
            path=data["upload-path"],
            push_task_method=self.push_task,  # To allow the services push anothers services call
            **kwargs,
        )

        # Add the task to the executor
        self.executor.schedule(task, on_end_callback=self._on_task_end)

        if task == None:
            await app.send_message(user, f"{emoji.CROSS_MARK} Unable to start task")
            return

        async with self.tasks_lock:
            self.tasks[task] = await app.send_message(
                user,
                f"Waiting to process this action ({task.id})",
                reply_markup=InlineKeyboardMarkup(
                    [[self.cancel_group.add(task.id, cachable=True).button("Cancel")]]
                ),
            )

            self.tasks_id[task.id] = task

    async def _updater(self):
        async with self.tasks_lock:
            for task, message in self.tasks.items():
                state, description = task.state

                if state == TaskState.ERROR or state == TaskState.SUCCESSFULL:
                    continue

                if description is None:
                    continue

                current, total = task.progress
                if (current or total) is not None:
                    current_text = (
                        naturalsize(current, binary=True, format="%.3f")
                        if current is not None
                        else "Unknown"
                    )
                    total_text = (
                        naturalsize(total, binary=True, format="%.3f")
                        if total is not None
                        else "Unknown"
                    )

                    speed = task.speed
                    eta = task.eta

                    speed_text = (
                        utils.get_str(naturalsize(speed, binary=True))
                        if speed is not None
                        else "Unknown"
                    )
                    eta_text = (
                        utils.get_str(naturaldelta(eta))
                        if eta is not None
                        else "Unknown"
                    )

                    text = f"{description} ({current_text} / {total_text})\nSpeed: {speed_text}/sec\nETA: {eta_text}"
                else:
                    text = f"{description}"

                # Walk to task childs (1 depth level)
                childs = task.childs()
                if len(childs) > 0:
                    text += "\n\n"

                    for child in childs:
                        s, d = child.state
                        c, t = task.progress
                        c_text = (
                            naturalsize(c, binary=True, format="%.3f")
                            if c is not None
                            else "Unknown"
                        )
                        t_text = (
                            naturalsize(t, binary=True, format="%.3f")
                            if t is not None
                            else "Unknown"
                        )

                        match s:
                            case TaskState.ERROR | TaskState.CANCELLED:
                                e = emoji.RED_CIRCLE
                            case TaskState.SUCCESSFULL:
                                e = emoji.GREEN_CIRCLE
                            case TaskState.WORKING | TaskState.WAITING | TaskState.STARTING:
                                e = emoji.YELLOW_CIRCLE

                        text += f"{e} {d} [{c_text} / {t_text}]\n"

                if message.text != text:
                    message.text = text
                    await message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup(
                            [
                                [
                                    self.cancel_group.add(
                                        task.id, cachable=True
                                    ).button(f"{emoji.HOLLOW_RED_CIRCLE} Cancel")
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

    async def status(self, app: Client, message: Message):
        user = message.from_user.id

        active = self.executor.active_count
        total = self.executor.total_count

        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        await app.send_message(
            user,
            "**Status:**\n\n"
            f"{emoji.CLOCKWISE_VERTICAL_ARROWS} Boot time: {naturaldelta(psutil.boot_time())}\n"
            f"{emoji.ELECTRIC_PLUG} CPU: {psutil.cpu_count()} cores\n"
            f"{emoji.BATTERY} RAM: {naturalsize(memory.used)} used of {naturalsize(memory.total)} [{memory.percent}%]\n"
            f"{emoji.FILE_FOLDER} Disk: {naturalsize(disk.used)} used of {naturalsize(disk.total)}\n"
            "\n"
            f"{emoji.YELLOW_CIRCLE} Active tasks: {active}\n"
            f"{emoji.BLUE_CIRCLE} Total tasks: {total}",
        )

    def register(self, app: Client):
        self.app = app

        # Add to scheduler updater function
        self.scheduler.add_job(self._updater, "interval", seconds=3, max_instances=1)

        handlers = [
            # MessageHandler(self.urls_batch, filters.command("batch")),
            MessageHandler(self.status, filters.command("status")),
            self.cancel_group.callback_handler(self.cancel_upload),
            MessageHandler(self.upload_file),
        ]

        for u in handlers:
            app.add_handler(u)
