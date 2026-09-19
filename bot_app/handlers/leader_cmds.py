import datetime

from .. import database, utils, chat_utils, config
from ..bot_instance import bot
from ..hierarchy import can_moderate, role_title
from ..permissions import check_access
from ..rules import CommandRule
from ..commands_meta import names
from .. import keyboards


@bot.on.message(CommandRule(names("clear")))
async def cmd_clear(message):
    """
    /clear (алиас "чистка") - ответом на сообщение пользователя удаляет это
    сообщение. Нельзя удалить сообщение того, чья роль выше или равна роли
    вызвавшего команду (кроме Создателя).
    """
    if not await check_access(message, "leader"):
        return

    reply = getattr(message, "reply_message", None)
    if reply is None:
        await utils.reply_msg(message, "Ответьте на сообщение, которое нужно удалить.")
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    actor_role = await database.get_effective_role(message.from_id, chat_id)
    target_role = await database.get_effective_role(reply.from_id, chat_id)
    if not can_moderate(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    try:
        await message.ctx_api.messages.delete(
            conversation_message_ids=[reply.conversation_message_id],
            peer_id=message.peer_id,
            delete_for_all=1,
        )
    except Exception:
        await utils.reply_msg(message, "Не удалось удалить сообщение (оно уже удалено или прошло много времени).")
        return

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    await utils.reply_msg(message, f"{actor_link} очистил(-а) сообщение(-я)!")


@bot.on.message(CommandRule(names("kick")))
async def cmd_kick(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, reason = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    actor_role = await database.get_effective_role(message.from_id, chat_id)
    target_role = await database.get_effective_role(target_id, chat_id)
    if not can_moderate(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    ok = await chat_utils.kick_member(message.ctx_api, message.peer_id, target_id)
    if not ok:
        await utils.reply_msg(message, "Не удалось исключить пользователя (нет прав администратора беседы?).")
        return

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    await utils.reply_msg(message, 
        f"{actor_link} кикнул(-а) {target_link}.\nПричина: {reason or '-'}"
    )


@bot.on.message(CommandRule(names("mute")))
async def cmd_mute(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    actor_role = await database.get_effective_role(message.from_id, chat_id)
    target_role = await database.get_effective_role(target_id, chat_id)
    if not can_moderate(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    minutes = utils.parse_duration_minutes(rest)
    if minutes is None:
        await utils.reply_msg(message, "Укажите время мута в минутах: /mute [тег] [минуты] [причина]")
        return
    reason = rest.split(str(minutes), 1)[-1].strip() if str(minutes) in rest else ""

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    until = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
    await database.add_mute(target_id, chat_id, message.from_id, reason, until)

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    kb = keyboards.punishment_keyboard("unmute", target_id, chat_id=chat_id)
    await utils.reply_msg(
        message,
        f"{actor_link} замутил(-а) {target_link}.\n"
        f"Мут выдан до {utils.format_dt(until)}\n"
        f"Причина: {reason or '-'}",
        keyboard=kb,
    )


@bot.on.message(CommandRule(names("unmute")))
async def cmd_unmute(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    await database.remove_mute(target_id, chat_id)

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    await utils.reply_msg(message, f"{actor_link} размутил(-а) {target_link}.")


@bot.on.message(CommandRule(names("staff")))
async def cmd_staff(message):
    if not await check_access(message, "leader"):
        return
    rows = await database.list_staff()
    if not rows:
        await utils.reply_msg(message, "Пользователей с ролями пока нет.")
        return

    from ..hierarchy import ROLE_TITLES
    grouped = {}
    for row in rows:
        grouped.setdefault(row["role"], []).append(row["vk_id"])

    blocks = []
    for role_key in ["creator", "leadership", "senior_tracker", "tracker", "leader", "senior_staff"]:
        ids = grouped.get(role_key)
        if not ids:
            continue
        links = []
        for vk_id in ids:
            links.append(await utils.profile_link_auto(message.ctx_api, vk_id))
        blocks.append(f"{ROLE_TITLES[role_key]}:\n" + "\n".join(links))

    await utils.reply_msg(message, "\n\n".join(blocks))


@bot.on.message(CommandRule(names("setnick")))
async def cmd_setnick(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя, укажите тег или ссылку.")
        return
    nickname = rest.strip()
    if not nickname:
        await utils.reply_msg(message, "Укажите ник: /setnick [тег/ссылка/ответ] [ник]")
        return

    existing = await database.find_by_nickname(nickname)
    if existing and existing["vk_id"] != target_id:
        await utils.reply_msg(message, f"Ник «{nickname}» уже занят другим пользователем.")
        return

    await database.set_nickname(target_id, nickname)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    await utils.reply_msg(message, f"{target_link} — установлен ник «{nickname}».")


@bot.on.message(CommandRule(names("removenick")))
async def cmd_removenick(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя, укажите тег или ссылку.")
        return

    current = await database.get_nickname(target_id)
    if not current:
        await utils.reply_msg(message, "У пользователя нет ника.")
        return

    await database.set_nickname(target_id, None)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    await utils.reply_msg(message, f"{target_link} — ник «{current}» удалён.")


@bot.on.message(CommandRule(names("getacc")))
async def cmd_getacc(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    nickname = args.strip()
    if not nickname:
        await utils.reply_msg(message, "Использование: /getacc NickName")
        return
    row = await database.find_by_nickname(nickname)
    if not row:
        await utils.reply_msg(message, f"Ник {nickname} никому не принадлежит.")
        return
    link = await utils.profile_link_auto(message.ctx_api, row["vk_id"])
    await utils.reply_msg(message, f"Ник {nickname} принадлежит — {link}")


@bot.on.message(CommandRule(names("getban")))
async def cmd_getban(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя, укажите тег или ссылку vk.com/idXXXX.")
        return

    lines = []

    global_ban = await database.get_global_ban(target_id)
    lines.append("Информация о глобальных блокировках:")
    if global_ban:
        mod_link = utils.role_label_link(global_ban["moderator_id"], "Модератор")
        created = utils.format_msk(global_ban["created_at"])
        lines.append(f"Присутствует | {mod_link} | {global_ban['reason'] or '-'} | {created}")
    else:
        lines.append("Отсутствует")
    lines.append("")

    pull_bans = await database.list_pull_bans_for_user(target_id)
    lines.append("Информация о блокировках в сетке беседы:")
    if pull_bans:
        for i, b in enumerate(pull_bans, 1):
            mod_link = utils.role_label_link(b["moderator_id"], "Модератор")
            lines.append(f"{i}. Сетка {b['pull_id']} | {mod_link} | {b['reason'] or '-'} | {utils.format_msk(b['created_at'])}")
    else:
        lines.append("Отсутствует")
    lines.append("")

    chat_bans = await database.list_chat_bans_for_user(target_id)
    lines.append("Информация о блокировке в беседах:")
    if chat_bans:
        for i, b in enumerate(chat_bans, 1):
            mod_link = utils.role_label_link(b["moderator_id"], "Модератор")
            title = b["chat_title"] or f"Беседа {b['chat_id']}"
            lines.append(f"{i}. {title} | {mod_link} | {b['reason'] or '-'} | {utils.format_msk(b['created_at'])}")
    else:
        lines.append("Отсутствует")

    await utils.reply_msg(message, "\n".join(lines))


@bot.on.message(CommandRule(names("skick")))
async def cmd_skick(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, reason = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    actor_role = await database.get_effective_role(message.from_id, chat_id)
    target_role = await database.get_effective_role(target_id, chat_id)
    if not can_moderate(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    pull_id = await database.get_pull_of_chat(chat_id)
    if pull_id is None:
        await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке (см. /setpull).")
        return

    chat_ids = await database.get_chats_in_pull_chain(pull_id)
    kicked_from = []
    for cid in chat_ids:
        ok = await chat_utils.kick_member(message.ctx_api, chat_utils.peer_from_chat_id(cid), target_id)
        if ok:
            kicked_from.append(cid)

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    text = f"{actor_link} кикнул(-а) {target_link} в сетке бесед.\nПричина: {reason or '-'}"
    await chat_utils.broadcast(message.ctx_api, kicked_from, text)


async def _send_zov(message, target_ids, reason: str, title_prefix: str = "🔔 Вы были вызваны"):
    actor_link = utils.role_label_link(message.from_id, "администратором")
    mentions = []
    for vk_id in target_ids:
        if vk_id == message.from_id:
            continue
        mentions.append(f"[id{vk_id}|🖤]")
    body = " ".join(mentions) if mentions else "(нет участников)"
    text = (
        f"{title_prefix} {actor_link} беседы.\n\n"
        f"{body}\n\n"
        f"❗️Причина вызова: {reason or '-'}"
    )
    await message.answer(text)


@bot.on.message(CommandRule(names("zov")))
async def cmd_zov(message):
    if not await check_access(message, "leader"):
        return
    _, reason = utils.parse_command(message.text)
    member_ids = await chat_utils.get_all_member_ids(message.ctx_api, message.peer_id)
    await _send_zov(message, member_ids, reason)


@bot.on.message(CommandRule(names("online")))
async def cmd_online(message):
    if not await check_access(message, "leader"):
        return
    _, reason = utils.parse_command(message.text)
    online_ids = await chat_utils.get_online_member_ids(message.ctx_api, message.peer_id)
    actor_link = utils.role_label_link(message.from_id, "администратором")
    mentions = [f"[id{vk_id}|♦]" for vk_id in online_ids if vk_id != message.from_id]
    body = " ".join(mentions) if mentions else "(никого нет онлайн)"
    text = (
        f"🔔 Кто онлайн? Вы были вызваны {actor_link} беседы.\n\n"
        f"{body}\n\n"
        f"❗️Причина вызова: {reason or '-'}"
    )
    await message.answer(text)


@bot.on.message(CommandRule(names("onlinelist")))
async def cmd_onlinelist(message):
    if not await check_access(message, "leader"):
        return
    online_ids = await chat_utils.get_online_member_ids(message.ctx_api, message.peer_id)
    online_ids = [vk_id for vk_id in online_ids if vk_id != message.from_id]
    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)

    if not online_ids:
        await message.answer(f"{actor_link}, список пользователей онлайн:\n\nВсего онлайн: 0")
        return

    lines = [f"{actor_link}, список пользователей онлайн:", ""]
    for vk_id in online_ids:
        lines.append(await utils.profile_link_auto(message.ctx_api, vk_id))
    lines.append("")
    lines.append(f"Всего онлайн: {len(online_ids)}")
    await message.answer("\n".join(lines))


@bot.on.message(CommandRule(names("warn")))
async def cmd_warn(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, reason = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    actor_role = await database.get_effective_role(message.from_id, chat_id)
    target_role = await database.get_effective_role(target_id, chat_id)
    if not can_moderate(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    total = await database.add_warn(target_id, message.from_id, reason)

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    kb = keyboards.punishment_keyboard("unwarn", target_id)
    await utils.reply_msg(
        message,
        f"{actor_link} выдал(-а) предупреждение {target_link}.\n"
        f"Причина: {reason or '-'}\n"
        f"Активных предупреждений: {total}",
        keyboard=kb,
    )


@bot.on.message(CommandRule(names("unwarn")))
async def cmd_unwarn(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    removed = await database.remove_latest_warn(target_id, message.from_id)
    if removed is None:
        await utils.reply_msg(message, "У пользователя нет активных предупреждений.")
        return

    remaining = await database.count_active_warns(target_id)
    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    await utils.reply_msg(message, 
        f"{actor_link} снял(-а) предупреждение с {target_link}.\n"
        f"Осталось активных предупреждений: {remaining}"
    )


@bot.on.message(CommandRule(names("getwarn")))
async def cmd_getwarn(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        target_id = message.from_id

    rows = await database.list_active_warns(target_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)

    if not rows:
        await utils.reply_msg(message, f"У {target_link} нет активных предупреждений.")
        return

    lines = [f"Активные предупреждения {target_link}:"]
    for i, row in enumerate(rows, 1):
        mod_link = await utils.profile_link_auto(message.ctx_api, row["moderator_id"])
        lines.append(f"{i}. {row['reason'] or '-'} | {mod_link} | {utils.format_msk(row['created_at'])}")
    lines.append(f"\nВсего активных: {len(rows)}")
    await utils.reply_msg(message, "\n".join(lines))


@bot.on.message(CommandRule(names("warnhistory")))
async def cmd_warnhistory(message):
    if not await check_access(message, "leader"):
        return
    _, args = utils.parse_command(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        target_id = message.from_id

    rows = await database.list_warn_history(target_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)

    if not rows:
        await utils.reply_msg(message, f"У {target_link} нет предупреждений в истории.")
        return

    lines = [f"История предупреждений {target_link}:"]
    for i, row in enumerate(rows, 1):
        mod_link = await utils.profile_link_auto(message.ctx_api, row["moderator_id"])
        status = "активен" if row["active"] else "снят"
        line = f"{i}. {row['reason'] or '-'} | выдал: {mod_link} | {utils.format_msk(row['created_at'])} | статус: {status}"
        if not row["active"] and row["removed_by"]:
            remover_link = await utils.profile_link_auto(message.ctx_api, row["removed_by"])
            line += f" (снял: {remover_link}, {utils.format_msk(row['removed_at'])})"
        lines.append(line)
    await utils.reply_msg(message, "\n".join(lines))


@bot.on.message(CommandRule(names("warnlist")))
async def cmd_warnlist(message):
    if not await check_access(message, "leader"):
        return
    rows = await database.list_users_with_active_warns()
    if not rows:
        await utils.reply_msg(message, "Ни у кого нет активных предупреждений.")
        return

    lines = ["Пользователи с предупреждениями:"]
    for row in rows:
        link = await utils.profile_link_auto(message.ctx_api, row["vk_id"])
        lines.append(f"{link} — {row['cnt']}")
    await utils.reply_msg(message, "\n".join(lines))
