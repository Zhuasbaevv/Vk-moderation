"""
Команды, доступные старшему составу и выше: /stats, /getid, /info, /help, /alt.
/getid по правилам проекта доступен вообще всем, включая создателя.
"""
from .. import database, utils, chat_utils, config
from ..bot_instance import bot
from ..hierarchy import role_title, can_view_stats, has_min_role, ROLE_ORDER
from ..permissions import check_access
from ..rules import CommandRule
from ..commands_meta import names, HELP_SECTIONS
from ..site_client import fetch_site_profile


@bot.on.message(CommandRule(names("getid")))
async def cmd_getid(message):
    """
    /getid [ответ на сообщение | @тег]
    Доступна абсолютно всем ролям.
    """
    _, args = _split(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Укажите пользователя: ответом на сообщение или тегом.")
        return
    link = await utils.profile_link_auto(message.ctx_api, target_id)
    await utils.reply_msg(message, 
        f"Оригинальная ссылка {link}:\nhttps://vk.com/id{target_id}"
    )


@bot.on.message(CommandRule(names("info")))
async def cmd_info(message):
    if not await check_access(message, "senior_staff"):
        return
    text = await database.get_info_text()
    if not text:
        text = "Информация о проекте пока не настроена. Используйте /setinfo, чтобы задать текст."
    await utils.reply_msg(message, text)


@bot.on.message(CommandRule(names("stats")))
async def cmd_stats(message):
    if not await check_access(message, "senior_staff"):
        return

    _, args = _split(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        target_id = message.from_id

    actor_role = await database.get_effective_role(message.from_id, chat_utils.chat_id_from_peer(message.peer_id))
    target_role = await database.get_effective_role(target_id, chat_utils.chat_id_from_peer(message.peer_id))

    if target_id != message.from_id and not can_view_stats(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    await database.ensure_user(target_id)
    user_row = await database.get_user_row(target_id)
    nickname = user_row["nickname"] or "Нет"
    days = utils.days_since(user_row["first_seen"])
    msg_today, msg_week, msg_all = await database.get_total_messages(target_id)
    mutes = await database.count_mutes(target_id)
    bans = await database.count_bans(target_id)
    last_online = utils.format_msk(user_row["last_online"])
    name = await utils.get_user_name(message.ctx_api, target_id)

    site_lines = ""
    site_profile = await fetch_site_profile(target_id)
    if site_profile and site_profile.get("position"):
        position = site_profile["position"]
        site_lines = f"\nДолжность: {position}"
        if position == "Старший состав" and site_profile.get("rank"):
            site_lines += f"\nРанг: {site_profile['rank']}"
        # Организацию показываем только для рядовых ролей (Старший состав, Лидер,
        # Следящий) - у Старшего следящего/Руководства/Создателя нет одной
        # конкретной организации (направление/всё целиком), поэтому строка
        # была бы бессмысленной или пустой.
        if position in ("Старший состав", "Лидер", "Следящий") and site_profile.get("org"):
            site_lines += f"\nОрганизация: {site_profile['org']}"
        site_lines += "\n"

    text = (
        "━━━━━━━━━━━━━━━━━━\n"
        "СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"ID: {target_id}\n"
        f"Ник: {nickname}\n"
        f"Имя: {name}\n"
        f"Роль: {role_title(target_role)}\n"
        f"{site_lines}"
        f"В системе: {days} дн.\n\n"
        "АКТИВНОСТЬ\n"
        f"Сегодня: {msg_today}\n"
        f"Неделя: {msg_week}\n"
        f"Всего: {msg_all}\n\n"
        "НАКАЗАНИЯ\n"
        f"Муты: {mutes}\n"
        f"Баны: {bans}\n\n"
        f"Последняя активность: {last_online}\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    await utils.reply_msg(message, text)


@bot.on.message(CommandRule(names("alt")))
async def cmd_alt(message):
    if not await check_access(message, "senior_staff"):
        return
    lines = ["Альтернативные написания команд:\n"]
    for cmd, alias_list in {
        "stats": ["стата", "статистика"],
        "getid": ["ид", "id"],
        "info": ["инфо"],
        "help": ["хелп", "помощь"],
        "kick": ["кик"],
        "mute": ["мут"],
        "unmute": ["унмут"],
        "alt": ["альт"],
        "staff": ["стафф", "admin"],
        "getban": ["чекбан"],
        "nlist": ["ники"],
        "getacc": ["узнать"],
        "skick": ["снят"],
        "zov": ["зов", "вызвать"],
        "online": ["онлайн"],
        "onlinelist": ["olist"],
        "ban": ["бан"],
        "unban": ["унбан"],
        "quiet": ["тишина"],
    }.items():
        lines.append(f"/{cmd} - {', '.join(alias_list)}")
    await utils.reply_msg(message, "\n".join(lines))


@bot.on.message(CommandRule(names("help")))
async def cmd_help(message):
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    role = await database.get_effective_role(message.from_id, chat_id)
    role_idx = ROLE_ORDER.index(role) if role in ROLE_ORDER else 0

    if role_idx == 0:
        await utils.reply_msg(message, 
            "Команды пользователей:\n"
            "/getid — узнать оригинальный ID пользователя в ВК"
        )
        return

    blocks = []
    for min_role, title, commands in HELP_SECTIONS:
        if has_min_role(role, min_role):
            lines = [f"{title}:"]
            for cmd, desc in commands:
                lines.append(f"/{cmd} - {desc}")
            blocks.append("\n".join(lines))

    await utils.reply_msg(message, "\n\n".join(blocks))


def _split(text: str):
    from ..utils import parse_command
    return parse_command(text)
