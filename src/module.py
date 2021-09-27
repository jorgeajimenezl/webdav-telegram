from pyrogram import Client

from context import UserContext
from database import Database


class Module(object):
    def __init__(self, context: UserContext, database: Database) -> None:
        self.context = context
        self.database = database

    def register_app(self, app: Client):
        raise NotImplementedError
