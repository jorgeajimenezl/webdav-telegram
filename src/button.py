import random
from dataclasses import dataclass, field
from typing import Any, Callable, Union

from pyrogram import filters
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.types import InlineKeyboardButton


@dataclass
class GroupButton(object):
    group: str
    value: Any

    # Private
    prefix: bytes
    map: bytes

    def button(self, text: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text, callback_data=(self.prefix + self.map))

    def callback_handler(self, func: Callable):
        return CallbackQueryHandler(func, filters=self.filter())

    def filter(self):
        return filters.create(
            lambda flt, _, query: query.data == flt.data, data=(self.prefix + self.map)
        )


@dataclass
class ActionButton(object):
    name: str

    # Private
    map: bytes

    def button(self, text: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text, callback_data=self.map)

    def callback_handler(self, func: Callable):
        return CallbackQueryHandler(func, filters=self.filter())

    def filter(self):
        return filters.create(
            lambda flt, _, query: query.data == flt.data, data=self.map
        )


@dataclass
class Group(object):
    name: str

    # Private
    prefix: bytes
    _factory: "ButtonFactory"
    _cache: dict = field(init=False, default_factory=dict)

    def add(self, value: Any, cachable: bool = False) -> GroupButton:
        if cachable and value in self._cache:
            return self._cache[value]

        u = random.randbytes(64 - len(self.prefix))
        m = self.prefix + u

        button = GroupButton(self.name, value, self.prefix, u)

        if cachable:
            self._cache[value] = button
        self._factory.buttons[m] = button

        return button

    def callback_handler(self, func: Callable):
        return CallbackQueryHandler(func, filters=self.filter())

    def filter(self):
        return filters.create(
            lambda flt, _, query: query.data.startswith(flt.data), data=self.prefix
        )


class ButtonFactory(object):
    def __init__(self) -> None:
        self.buttons = dict()
        self.groups = dict()

    def create_action(self, name: str) -> ActionButton:
        u = random.randbytes(64)
        self.buttons[u] = ActionButton(name, u)
        return self.buttons[u]

    def create_group(self, name: str, prefix_len: int = 20) -> Group:
        prefix = random.randbytes(prefix_len)
        self.groups[name] = Group(name, prefix, self)

        return self.groups[name]

    def get(self, map: bytes) -> Union[GroupButton, ActionButton]:
        return self.buttons[map]

    def get_value(self, map: bytes) -> Any:
        if isinstance(self.buttons[map], ActionButton):
            return self.buttons[map].name
        return self.buttons[map].value
