import asyncio
from types import SimpleNamespace
from typing import Any, Callable, List, Tuple, TypeVar, Union

from pyrogram import Client, emoji
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
)

from button import ButtonFactory, GroupButton

T = TypeVar("T")


async def selection(
    app: Client,
    user: int,
    options: List[T],
    description: str = "Select",
    multi_selection: bool = True,
    name_selector: Callable[[T], str] = None,
    max_options_per_page: int = 8,
    message: Message = None,
    delete: bool = True,
    cancellable: bool = True,
) -> Union[T, List[T], Tuple[List[T], Message]]:
    ns = SimpleNamespace(page=0, cancelled=False, options=[])

    lock = asyncio.Lock()
    event = asyncio.Event()

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
        selected = button.value in ns.options
        return [button.button(f"{emoji.CHECK_MARK if selected else ''}{name}")]

    def navigation_buttons():
        ret = []

        if ns.page > 0:
            ret.append(back_button.button(f"{emoji.LEFT_ARROW} {ns.page - 1}"))
        if ns.page < total_pages - 1:
            ret.append(next_button.button(f"{ns.page + 1} {emoji.RIGHT_ARROW}"))

        return ret

    async def select_callback(app: Client, callback_query: CallbackQuery):
        async with lock:
            a = ns.page * max_options_per_page
            b = min(len(options), (ns.page + 1) * max_options_per_page)

            extra = [
                [
                    selectall_button.button("Select all"),
                    unselectall_button.button("Unselect all"),
                ],
                (
                    [
                        done_button.button(f"{emoji.CHECK_MARK_BUTTON} DONE"),
                        cancel_button.button(f"{emoji.CROSS_MARK_BUTTON} CANCEL"),
                    ]
                    if cancellable
                    else [done_button.button(f"{emoji.CHECK_MARK_BUTTON} DONE")]
                ),
            ]
            navigation = navigation_buttons()
            markup = InlineKeyboardMarkup(
                [create_button(opt) for opt in items[a:b]]
                + ([navigation] if len(navigation) > 0 else [])
                + (
                    extra
                    if multi_selection
                    else ([[cancel_button.button("Cancel")]] if cancellable else [[]])
                )
            )

            if callback_query is None:
                if message is None:
                    return await app.send_message(
                        user, description, reply_markup=markup
                    )
                else:
                    await message.edit(description, reply_markup=markup)
                    return message
            else:
                await callback_query.edit_message_reply_markup(markup)

    async def select_all_callback(app: Client, callback_query: CallbackQuery):
        async with lock:
            ns.options = options.copy()
        await select_callback(app, callback_query)

    async def unselect_all_callback(app: Client, callback_query: CallbackQuery):
        async with lock:
            ns.options.clear()
        await select_callback(app, callback_query)

    async def next_page_callback(app: Client, callback_query: CallbackQuery):
        async with lock:
            if ns.page < total_pages - 1:
                ns.page += 1
        await select_callback(app, callback_query)

    async def back_page_callback(app: Client, callback_query: CallbackQuery):
        async with lock:
            if ns.page > 0:
                ns.page -= 1
        await select_callback(app, callback_query)

    async def done_callback(_, callback_query: CallbackQuery):
        if delete:
            await callback_query.message.delete(True)
        event.set()

    async def cancel_callback(_, callback_query: CallbackQuery):
        if delete:
            await callback_query.message.delete(True)
        async with lock:
            ns.cancelled = True
        event.set()

    async def select_item_callback(app: Client, callback_query: CallbackQuery):
        m = factory.get(callback_query.data).value

        async with lock:
            if m in ns.options:
                ns.options.remove(m)
            else:
                ns.options.append(m)

        if multi_selection:
            await select_callback(app, callback_query)
        else:
            await done_callback(app, callback_query)

    handlers = [
        select_group.callback_handler(select_item_callback),
        next_button.callback_handler(next_page_callback),
        back_button.callback_handler(back_page_callback),
        selectall_button.callback_handler(select_all_callback),
        unselectall_button.callback_handler(unselect_all_callback),
        done_button.callback_handler(done_callback),
        cancel_button.callback_handler(cancel_callback),
    ]

    # Add temporal handlers for each button type
    for u in handlers:
        app.add_handler(u)

    # Send selection message
    message = await select_callback(app, None)

    # Wait to the selection
    await event.wait()

    # Delete temporal handlers
    for h in handlers:
        app.remove_handler(h)

    opt = ns.options

    if ns.cancelled:
        opt = None
    else:
        if not multi_selection:
            assert len(opt) == 1, "The selection must have only one element"
            opt = opt[0]

    return opt if delete else (opt, message)
