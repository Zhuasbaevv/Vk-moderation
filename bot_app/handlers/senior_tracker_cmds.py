from .. import database, utils, chat_utils, config, keyboards
from ..bot_instance import bot
from ..hierarchy import can_moderate
from ..permissions import check_access
from ..rules import CommandRule
from ..commands_meta import names


@bot.on.message(CommandRule(names("sban")))
async def cmd_sban(message):
    if not await check_access(message, "senior_tracker"):
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

    pull_id = await database.get_pull_of_chat(chat_id)
    if pull_id is None:
        await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке (см. /setpull).")
        return

    # Бан ставится на КАЖДУЮ сетку в цепочке (организация -> направление ->
    # холдинг), чтобы попытка зайти в любую из этих бесед позже тоже была
    # заблокирована (см. join_guard.py).
    chain = await database.get_pull_chain(pull_id)
    for pid in chain:
        await database.add_pull_ban(target_id, pid, message.from_id, reason)

    chat_ids = await database.get_chats_in_pull_chain(pull_id)
    kicked_from = []
    for cid in chat_ids:
        ok = await chat_utils.kick_member(message.ctx_api, chat_utils.peer_from_chat_id(cid), target_id)
        if ok:
            kicked_from.append(cid)

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    text = f"{actor_link} заблокировал(-а) {target_link} в сетке беседы.\nПричина: {reason or '-'}"
    kb = keyboards.punishment_keyboard("sunban", target_id, pull_id=pull_id)
    await chat_utils.broadcast(message.ctx_api, kicked_from, text, keyboard=kb)


@bot.on.message(CommandRule(names("sunban")))
async def cmd_sunban(message):
    if not await check_access(message, "senior_tracker"):
        return
    _, args = utils.parse_command(message.text)
    target_id, reason = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    pull_id = await database.get_pull_of_chat(chat_id)
    if pull_id is None:
        await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке (см. /setpull).")
        return

    chain = await database.get_pull_chain(pull_id)
    removed_any = False
    for pid in chain:
        removed = await database.remove_pull_ban(target_id, pid)
        removed_any = removed_any or removed

    if not removed_any:
        await utils.reply_msg(message, "У пользователя нет активной блокировки в этой сетке бесед.")
        return

    chat_ids = await database.get_chats_in_pull_chain(pull_id)
    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    text = f"{actor_link} разблокировал(-а) {target_link} в сетке беседы.\nПричина: {reason or '-'}"
    await chat_utils.broadcast(message.ctx_api, chat_ids, text)


@bot.on.message(CommandRule(names("szov")))
async def cmd_szov(message):
    if not await check_access(message, "senior_tracker"):
        return
    _, reason = utils.parse_command(message.text)

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    pull_id = await database.get_pull_of_chat(chat_id)
    if pull_id is None:
        await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке (см. /setpull).")
        return

    chat_ids = await database.get_chats_in_pull_chain(pull_id)
    actor_link = utils.role_label_link(message.from_id, "администратором")

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
