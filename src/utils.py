import asyncio
import random
import re
import itertools
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, Iterator, List, Set, Tuple, Union

from pyrogram import Client, emoji, filters
from pyrogram.handlers import CallbackQueryHandler
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from button import ButtonFactory, GroupButton

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F700-\U0001F77F"  # alchemical symbols
    "\U0001F780-\U0001F7FF"  # Geometric Shapes Extended
    "\U0001F800-\U0001F8FF"  # Supplemental Arrows-C
    "\U0001F900-\U0001F9FF"  # Supplemental Symbols and Pictographs
    "\U0001FA00-\U0001FA6F"  # Chess Symbols
    "\U0001FA70-\U0001FAFF"  # Symbols and Pictographs Extended-A
    "\U00002702-\U000027B0"  # Dingbats
    "\U000024C2-\U0001F251"
    "]+"
)

WEBDAV_REMOVE_CHARACTERS = "&%?="


def strip_emoji(x: str) -> str:
    return EMOJI_PATTERN.sub(r"", x)


def sanitaze_filename(x: str) -> str:
    x = strip_emoji(x)
    for c in WEBDAV_REMOVE_CHARACTERS:
        x = x.replace(c, "")
    return x


def get_str(x: str) -> str:
    return x if x != None else "Unknown"


def get_bool(x: str) -> bool:
    if isinstance(x, bool):
        return x

    x = x.lower()
    if x in ["on", "true", "activate", "right"]:
        return True
    if x in ["off", "false", "desactivate", "wrong"]:
        return False

    raise ValueError("Impossible convert from this string to bool")


def cut(x: str, length: int) -> List[str]:
    ret = []
    while x != "":
        ret.append(x[:length])
        x = x[length:]
    return ret


def expand_ranges(x: str) -> Iterator[str]:
    ranges = []

    for match in re.finditer("\{([\d\-,A-Za-z&\.]+)\}", x):
        items = match[1].split(",")
        r = []

        for item in items:
            item = item.strip()

            if "-" in item:
                m = re.fullmatch("(\d+)-(\d+)", item)
                if not m:
                    raise Exception(f"Invalid range operation: line({match.start()})")
                r.extend(range(int(m[1]), int(m[2]) + 1))
            else:
                r.append(item)

        ranges.append(r)
    x = re.sub("\{([\d\-,A-Za-z&\.]+)\}", "{}", x)

    for t in itertools.product(*ranges):
        yield x.format(*t)


async def selection(
    app: Client,
    user: int,
    options: List[Any],
    message_text: str = "Select",
    multi_selection: bool = True,
    name_selector: Callable[[Any], str] = None,
    max_options_per_page: int = 8,
    message: Message = None,
    delete: bool = True,
) -> Union[List[Any], Tuple[List[Any], Message]]:
    ns = SimpleNamespace()
    opt = list()

    event = asyncio.Event()
    ns.page = 0
    ns.canceled = False

    total_pages = len(options) // max_options_per_page + (
        1 if len(options) % max_options_per_page != 0 else 0
    )

    factory = ButtonFactory()
    select_group = factory.create_group("select")
    items = [select_group.add(k) for k in options]

    next_button = factory.create_action("next")
    back_button = factory.create_action("back")
    selectall_button = factory.create_action("select-all")
    unselectall_button = factory.create_action("unselect-all")
    done_button = factory.create_action("done")
    cancel_button = factory.create_action("cancel")

    def create_button(button: GroupButton):
        name = button.value
        if callable(name_selector):
            name = name_selector(name)
        name = str(name)

        if len(name) >= 20:
            name = name[:40]
        selected = button.value in opt
        return [button.button(f"{emoji.CHECK_MARK if selected else ''}{name}")]

    def navigation_buttons():
        ret = []

        if ns.page > 0:
            ret.append(back_button.button(f"{emoji.LEFT_ARROW} {ns.page - 1}"))
        if ns.page < total_pages - 1:
            ret.append(next_button.button(f"{ns.page + 1} {emoji.RIGHT_ARROW}"))

        return ret

    async def _select(app: Client, callback_query: CallbackQuery):
        a = ns.page * max_options_per_page
        b = min(len(options), (ns.page + 1) * max_options_per_page)

        extra = [
            [
                selectall_button.button("Select all"),
                unselectall_button.button("Unselect all"),
            ],
            [
                done_button.button(f"{emoji.CHECK_MARK_BUTTON} DONE"),
                cancel_button.button(f"{emoji.CROSS_MARK_BUTTON} CANCEL"),
            ],
        ]
        navigation = navigation_buttons()
        markup = InlineKeyboardMarkup(
            [create_button(opt) for opt in items[a:b]]
            + ([navigation] if len(navigation) > 0 else [])
            + (extra if multi_selection else [[cancel_button.button("Cancel")]])
        )

        if callback_query == None:
            if message == None:
                return await app.send_message(user, message_text, reply_markup=markup)
            else:
                await message.edit(message_text, reply_markup=markup)
                return message
        else:
            await callback_query.edit_message_reply_markup(markup)

    async def _select_all(app: Client, callback_query: CallbackQuery):
        global opt
        opt = options.copy()
        await _select(app, callback_query)

    async def _unselect_all(app: Client, callback_query: CallbackQuery):
        opt.clear()
        await _select(app, callback_query)

    async def _next_page(app: Client, callback_query: CallbackQuery):
        if ns.page < total_pages - 1:
            ns.page += 1
        await _select(app, callback_query)

    async def _back_page(app: Client, callback_query: CallbackQuery):
        if ns.page > 0:
            ns.page -= 1
        await _select(app, callback_query)

    async def _done(_, callback_query: CallbackQuery):
        await callback_query.message.delete(True)
        event.set()

    async def _cancel(_, callback_query: CallbackQuery):
        await callback_query.message.delete(True)
        ns.canceled = True
        event.set()

    async def _select_item(app: Client, callback_query: CallbackQuery):
        m = factory.get(callback_query.data).value

        if m in opt:
            opt.remove(m)
        else:
            opt.append(m)

        if multi_selection:
            await _select(app, callback_query)
        else:
            if delete:
                await callback_query.message.delete(True)
            event.set()

    handlers = [
        select_group.callback_handler(_select_item),
        next_button.callback_handler(_next_page),
        back_button.callback_handler(_back_page),
        selectall_button.callback_handler(_select_all),
        unselectall_button.callback_handler(_unselect_all),
        done_button.callback_handler(_done),
        cancel_button.callback_handler(_cancel),
    ]

    # Add temporal handlers for each button type
    for u in handlers:
        app.add_handler(u)

    # Send selection message
    message = await _select(app, None)

    # Wait to the selection
    await event.wait()

    # Delete temporal handlers
    for h in handlers:
        app.remove_handler(h)

    if delete:
        return opt if not ns.canceled else None
    return (opt if not ns.canceled else None, message)
