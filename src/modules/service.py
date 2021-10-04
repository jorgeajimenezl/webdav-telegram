from pyrogram.types import Message

from async_executor.task import Task


class Service(Task):
    def __init__(
        self, id: int, user: int, file_message: Message, *args, **kwargs
    ) -> None:
        self.user = user
        self.file_message = file_message

        self.pyrogram = kwargs.get("pyrogram", file_message._client)
        self.split_size = kwargs.get("split_size", 100) * 1024 * 1024  # Bytes

        self.webdav_hostname = kwargs.get("hostname")
        self.webdav_username = kwargs.get("username")
        self.webdav_password = kwargs.get("password")
        self.webdav_path = kwargs.get("path")

        super().__init__(id, *args, **kwargs)

    @staticmethod
    def check(message: Message) -> bool:
        raise NotImplementedError
