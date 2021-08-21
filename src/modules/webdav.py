import asyncio
from executor import TaskExecutor
from module import Module
from context import UserContext
from database import Database
from tasks.telegram_to_webdav import TelegramToWebdav
from task import Task, TaskState

from pyrogram import Client, emoji, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.handlers import MessageHandler, CallbackQueryHandler


class WebdavModule(Module):
    def __init__(self, context: UserContext, database: Database,
                 executor: TaskExecutor, tasks: dict,
                 tasks_lock: asyncio.Lock) -> None:
        super().__init__(context, database)

        self.executor = executor
        self.app = None
        self.tasks = tasks
        self.tasks_lock = tasks_lock
        self.tasks_id = dict()

    async def _on_task_end(self, task: TelegramToWebdav):
        user = task.user
        state, description = task.state()

        if state == TaskState.ERROR or \
            state == TaskState.CANCELED:
            await self.app.send_message(
                user,
                description,
                reply_to_message_id=task.file_message.message_id)

        if state == TaskState.SUCCESSFULL:
            await self.app.send_message(
                user,
                f"{emoji.CHECK_MARK_BUTTON} Successfull",
                reply_to_message_id=task.file_message.message_id)

        async with self.tasks_lock:
            message = self.tasks.pop(task)
            self.tasks_id.pop(task.id)

            # Remove progress message
            try:
                if message != None:
                    await message.delete(True)
            except Exception:
                pass

    async def upload_url(self, app: Client, message: Message):
        user = message.from_user.id

        # try:
        #     url = message.command[-1]
        #     if not re.fullmatch(URL_REGEX_PATERN, url):
        #         raise Exception

        # except Exception:
        #     await app.send_message(
        #         user,
        #         'You must insert a valid url. Ex: **/download https://example.com/file.zip**'
        #     )
        #     context.update(user, CONTEXT['IDLE'])
        await app.send_message(user, "Unsupported method")

    async def cancel_upload(self, app: Client, callback_query: CallbackQuery):
        callback_query.answer("Sheduled stop", show_alert=True)
        _, _, id = callback_query.data.partition(' ')
        id = int(id)

        async with self.tasks_lock:
            if id in self.tasks_id:
                self.tasks_id[id].cancel()

    async def upload_file(self, app: Client, message: Message):
        user = message.from_user.id
        data = self.database.get_data(user)

        # upload
        task = self.executor.add(TelegramToWebdav,
                                 on_end_callback=self._on_task_end,
                                 user=user,
                                 file_message=message,
                                 split_size=int(data['split_size']),
                                 hostname=data['server'],
                                 username=data['user'],
                                 password=data['password'],
                                 path=data['upload_path'])

        self.tasks[task] = await app.send_message(
            user,
            f"Waiting to process this action (Task #{task.id})",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("Cancel",
                                     callback_data=f"cancel {task.id}")
            ]]))

        self.tasks_id[task.id] = task

    def register_app(self, app: Client):
        self.app = app

        handlers = [
            MessageHandler(
                self.upload_file, filters.document | filters.photo
                | filters.video | filters.audio),
            CallbackQueryHandler(self.cancel_upload,
                                 filters.regex('^cancel \d+$'))
        ]

        for u in handlers:
            app.add_handler(u)
