"""
/nlist и /nonick с пагинацией (50 на странице) и инлайн-кнопками
"пред. страница / переключить вид / след. страница". Рендер страницы
вынесен в отдельную функцию render_nick_page - её же использует
handlers/callbacks.py при нажатии на кнопки, чтобы не дублировать логику.
"""
from .. import database, utils
from ..bot_instance import bot
from ..permissions import check_access
from ..rules import CommandRule
from ..commands_meta import names
from ..keyboards import nick_keyboard, PAGE_SIZE


async def render_nick_page(ctx_api, view: str, page: int):
    """
    view: "nlist" (с никами) или "nonick" (без ников).
    Возвращает (текст, фактическая_страница, всего_страниц).
    """
    if view == "nlist":
        rows = await database.list_with_nicknames()
        header = "Список людей с никами:"
        empty_text = "Пользователей с никами пока нет."
    else:
        rows = await database.list_without_nicknames()
        header = "Пользователи без ников:"
        empty_text = "Все пользователи имеют ник."

    if not rows:
        return empty_text, 1, 1

    total_pages = max(1, (len(rows) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))
    chunk = rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]

    lines = [header]
    for row in chunk:
        link = await utils.profile_link_auto(ctx_api, row["vk_id"])
        if view == "nlist":
            lines.append(f"{link} - {row['nickname']}")
        else:
            lines.append(link)
    lines.append(f"\nСтраница {page}/{total_pages}")
    return "\n".join(lines), page, total_pages


@bot.on.message(CommandRule(names("nlist")))
async def cmd_nlist(message):
    if not await check_access(message, "leader"):
        return
    text, page, total_pages = await render_nick_page(message.ctx_api, "nlist", 1)
    kb = nick_keyboard("nlist", page, total_pages)
    await utils.reply_msg(message, text, keyboard=kb)


@bot.on.message(CommandRule(names("nonick")))
async def cmd_nonick(message):
    if not await check_access(message, "leader"):
        return
    text, page, total_pages = await render_nick_page(message.ctx_api, "nonick", 1)
    kb = nick_keyboard("nonick", page, total_pages)
    await utils.reply_msg(message, text, keyboard=kb)


@bot.on.message(CommandRule(names("getnick")))
async def cmd_getnick(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя, укажите тег или ссылку.")
        return

    nickname = await database.get_nickname(target_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    if not nickname:
        await utils.reply_msg(message, f"У {target_link} нет ника.")
        return
    await utils.reply_msg(message, f"Ник {target_link} — {nickname}")
