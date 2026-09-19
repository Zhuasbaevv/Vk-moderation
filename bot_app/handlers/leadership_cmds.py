from .. import database, utils, chat_utils, config, keyboards
from ..bot_instance import bot
from ..hierarchy import can_moderate
from ..permissions import check_global_access
from ..rules import CommandRule
from ..commands_meta import names


async def _all_known_chat_ids():
    """
    Все беседы, куда добавлен бот (авто-регистрация при первом сообщении/
    добавлении бота в беседу) - НЕ требует ручного /global. Команда /global
    при этом сохранена и работает как раньше, для своих целей.
    """
    return await database.list_known_chat_ids()


@bot.on.message(CommandRule(names("gban")))
async def cmd_gban(message):
    if not await check_global_access(message, "leadership"):
        return
    _, args = utils.parse_command(message.text)
    target_id, reason = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    actor_role = await database.get_role(message.from_id)
    target_role = await database.get_effective_role(
        target_id, chat_utils.chat_id_from_peer(message.peer_id)
    )
    if not can_moderate(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    await database.add_global_ban(target_id, message.from_id, reason)

    chat_ids = await _all_known_chat_ids()
    kicked_from = []
    for cid in chat_ids:
        ok = await chat_utils.kick_member(message.ctx_api, chat_utils.peer_from_chat_id(cid), target_id)
        if ok:
            kicked_from.append(cid)

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    text = f"{actor_link} заблокировал(-а) во всех беседах {target_link}.\nПричина: {reason or '-'}"
    kb = keyboards.punishment_keyboard("gunban", target_id)
    await chat_utils.broadcast(message.ctx_api, kicked_from, text, keyboard=kb)
    if not kicked_from:
        await utils.reply_msg(message, text, keyboard=kb)


@bot.on.message(CommandRule(names("gunban")))
async def cmd_gunban(message):
    if not await check_global_access(message, "leadership"):
        return
    _, args = utils.parse_command(message.text)
    target_id, reason = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    removed = await database.remove_global_ban(target_id)
    if not removed:
        await utils.reply_msg(message, "У пользователя нет активной глобальной блокировки.")
        return

    chat_ids = await _all_known_chat_ids()
    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    text = f"{actor_link} разблокировал(-а) во всех беседах {target_link}.\nПричина: {reason or '-'}"
    await chat_utils.broadcast(message.ctx_api, chat_ids, text)
    if not chat_ids:
        await utils.reply_msg(message, text)


@bot.on.message(CommandRule(names("gkick")))
async def cmd_gkick(message):
    if not await check_global_access(message, "leadership"):
        return
    _, args = utils.parse_command(message.text)
    target_id, reason = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    actor_role = await database.get_role(message.from_id)
    target_role = await database.get_effective_role(
        target_id, chat_utils.chat_id_from_peer(message.peer_id)
    )
    if not can_moderate(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    chat_ids = await _all_known_chat_ids()
    kicked_from = []
    for cid in chat_ids:
        ok = await chat_utils.kick_member(message.ctx_api, chat_utils.peer_from_chat_id(cid), target_id)
        if ok:
            kicked_from.append(cid)

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    text = f"{actor_link} кикнул(-а) во всех беседах {target_link}.\nПричина: {reason or '-'}"
    await chat_utils.broadcast(message.ctx_api, kicked_from, text)
    if not kicked_from:
        await utils.reply_msg(message, text)


@bot.on.message(CommandRule(names("gzov")))
async def cmd_gzov(message):
    if not await check_global_access(message, "leadership"):
        return
    _, reason = utils.parse_command(message.text)
    chat_ids = await _all_known_chat_ids()
    actor_link = utils.role_label_link(message.from_id, "администратором")

    if not chat_ids:
        await utils.reply_msg(message, "Бот пока не добавлен ни в одну беседу.")
        return

    for cid in chat_ids:
        peer_id = chat_utils.peer_from_chat_id(cid)
        member_ids = await chat_utils.get_all_member_ids(message.ctx_api, peer_id)
        mentions = [f"[id{vk_id}|🖤]" for vk_id in member_ids]
        body = " ".join(mentions) if mentions else "(нет участников)"
        text = (
            f"🔔 Вы были вызваны {actor_link} беседы.\n\n"
            f"{body}\n\n"
            f"❗️Причина вызова: {reason or '-'}"
        )
        try:
            await message.ctx_api.messages.send(peer_id=peer_id, message=text, random_id=0)
        except Exception:
            continue


@bot.on.message(CommandRule(names("leaveban")))
async def cmd_leaveban(message):
    """
    Переключает автобан за самостоятельный выход ИЗ ЭТОЙ КОНКРЕТНОЙ беседы.
    Если человек выйдет сам - при попытке вернуться (по кнопке "Вернуться"
    или через повторное приглашение) бот его сразу кикнет обратно.
    """
    if not await check_access(message, "leadership"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    new_state = await database.toggle_chat_leaveban(chat_id)
    action = "включён" if new_state else "выключен"
    await utils.reply_msg(message, f"Автобан за самостоятельный выход из ЭТОЙ беседы {action}.")


@bot.on.message(CommandRule(names("sleaveban")))
async def cmd_sleaveban(message):
    """То же самое, но на уровне сетки: самостоятельный выход из ЛЮБОЙ
    беседы сетки банит по всей цепочке сеток (как /sban)."""
    if not await check_access(message, "leadership"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    pull_id = await database.get_pull_of_chat(chat_id)
    if pull_id is None:
        await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке (см. /setpull).")
        return
    new_state = await database.toggle_pull_leaveban(pull_id)
    action = "включён" if new_state else "выключен"
    await utils.reply_msg(message, f"Автобан за самостоятельный выход из беседы в СЕТКЕ {action}.")


@bot.on.message(CommandRule(names("gleaveban")))
async def cmd_gleaveban(message):
    """Глобально: самостоятельный выход из ЛЮБОЙ известной беседы банит
    пользователя во всех беседах бота (как /gban). Только глобальная роль -
    как и остальные /g... команды."""
    if not await check_global_access(message, "leadership"):
        return
    new_state = await database.toggle_global_leaveban()
    action = "включён" if new_state else "выключен"
    await utils.reply_msg(message, f"Глобальный автобан за самостоятельный выход из беседы {action}.")


@bot.on.message(CommandRule(names("setinfo")))
async def cmd_setinfo(message):
    if not await check_global_access(message, "leadership"):
        return
    _, text = utils.parse_command(message.text)
    if not text.strip():
        await utils.reply_msg(message, "Использование: /setinfo [текст]")
        return
    await database.set_info_text(text.strip())
    await utils.reply_msg(message, "Успешно: написан текст для команды /info")
