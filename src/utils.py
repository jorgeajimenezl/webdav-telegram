from typing import Any, Dict, List, Set, Tuple, Union
from pyrogram import Client, emoji, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.handlers import CallbackQueryHandler
from types import SimpleNamespace
from button import ButtonFactory

import random, asyncio

URL_REGEX_PATTERN = 'https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)'

async def selection(app: Client,
                    user: int,
                    options: Dict[str, Any],
                    message: str = 'Select',
                    multi_selection: bool = True,
                    max_options_per_page: int = 8) -> Dict[str, Any]:
    ns = SimpleNamespace()
    opt = dict()

    ns.page = 0
    ns.done = False
    ns.canceled = False

    total_pages = len(options) // max_options_per_page \
                    + (1 if len(options) % max_options_per_page != 0 else 0)

    prefix = random.randbytes(20)
    rid = {prefix + random.randbytes(44): k for k in options}    

    next_id = random.randbytes(64)
    back_id = random.randbytes(64)
    select_all_id = random.randbytes(64)
    unselect_all_id = random.randbytes(64)
    done_id = random.randbytes(64)
    cancel_id = random.randbytes(64)

    exact_match = lambda data: filters.create(
        lambda flt, _, query: query.data == flt.data, data=data)
    starts_with = lambda data: filters.create(
        lambda flt, _, query: query.data.startswith(flt.data), data=data)

    def create_button(option: Tuple[str, bytes]):
        id, name = option
        if len(name) >= 20:
            name = name[:20]
        selected = (name in opt)
        return [
            InlineKeyboardButton(
                f"{emoji.CHECK_MARK_BUTTON if selected else ''}{name}",
                callback_data=id)
        ]

    def navigation_buttons():
        back = InlineKeyboardButton(f'{emoji.LEFT_ARROW} {ns.page - 1}',
                                    callback_data=back_id)
        next = InlineKeyboardButton(f'{ns.page + 1} {emoji.RIGHT_ARROW}',
                                    callback_data=next_id)
        ret = []
        if ns.page > 0:
            ret.append(back)
        if ns.page < total_pages - 1:
            ret.append(next)

        return ret

    items = list(rid.items())

    async def _select(app: Client, callback_query: CallbackQuery):
        a = ns.page * max_options_per_page
        b = min(len(options), (ns.page + 1) * max_options_per_page)
        page_items = items[a:b]

        # yapf: disable
        done_button = InlineKeyboardButton('Done', callback_data=done_id)
        cancel_button = InlineKeyboardButton('Cancel', callback_data=cancel_id)

        extra = [
            [
                InlineKeyboardButton('Select All', callback_data=select_all_id),
                InlineKeyboardButton('Unselect All', callback_data=unselect_all_id)
            ],
            [done_button, cancel_button]
        ]

        markup = InlineKeyboardMarkup(
            [create_button(opt) for opt in page_items] +
            [navigation_buttons()] + (extra if multi_selection else [cancel_button])
        )
        # yapf: enable

        if callback_query == None:
            await app.send_message(user, message, reply_markup=markup)
        else:
            await callback_query.edit_message_reply_markup(markup)

    async def _select_all(app: Client, callback_query: CallbackQuery):
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
        ns.done = True

    async def _cancel(_, callback_query: CallbackQuery):
        await callback_query.message.delete(True)
        ns.canceled = True
        ns.done = True

    async def _select_item(app: Client, callback_query: CallbackQuery):
        m = rid[callback_query.data]

        if m in opt:
            opt.pop(m)
        else:
            opt[m] = options[m]

        if multi_selection:
            await _select(app, callback_query)
        else:
            callback_query.message.delete(True)
            ns.done = True

    ret = [
        app.add_handler(
            CallbackQueryHandler(_select_item, filters=starts_with(prefix))),
        app.add_handler(
            CallbackQueryHandler(_next_page, filters=exact_match(next_id))),
        app.add_handler(
            CallbackQueryHandler(_back_page, filters=exact_match(back_id))),
        app.add_handler(
            CallbackQueryHandler(_select_all,
                                 filters=exact_match(select_all_id))),
        app.add_handler(
            CallbackQueryHandler(_unselect_all,
                                 filters=exact_match(unselect_all_id))),
        app.add_handler(
            CallbackQueryHandler(_done, filters=exact_match(done_id))),
        app.add_handler(
            CallbackQueryHandler(_cancel, filters=exact_match(cancel_id))),
    ]

    await _select(app, None)

    while not ns.done:
        await asyncio.sleep(0.5)

    for h, g in ret:
        app.remove_handler(h, g)

    return opt if not ns.canceled else None