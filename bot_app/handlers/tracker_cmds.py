from .. import database, utils, chat_utils, config, keyboards
from ..bot_instance import bot
from ..hierarchy import can_moderate
from ..permissions import check_access
from ..rules import CommandRule
from ..commands_meta import names


@bot.on.message(CommandRule(names("ban")))
async def cmd_ban(message):
    if not await check_access(message, "tracker"):
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
    title = await chat_utils.get_conversation_title(message.ctx_api, message.peer_id)
    await database.add_chat_ban(target_id, chat_id, title, message.from_id, reason)
    # Сразу же исключаем, если пользователь ещё состоит в беседе.
    await chat_utils.kick_member(message.ctx_api, message.peer_id, target_id)

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    kb = keyboards.punishment_keyboard("unban", target_id, chat_id=chat_id)
    await utils.reply_msg(
        message,
        f"{actor_link} заблокировал(-а) {target_link}.\nПричина: {reason or '-'}",
        keyboard=kb,
    )


@bot.on.message(CommandRule(names("unban")))
async def cmd_unban(message):
    if not await check_access(message, "tracker"):
        return
    _, args = utils.parse_command(message.text)
    target_id, reason = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    removed = await database.remove_chat_ban(target_id, chat_id)
    if not removed:
        await utils.reply_msg(message, "У пользователя нет активной блокировки в этой беседе.")
        return

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    target_name = await utils.get_user_name(message.ctx_api, target_id)
    await utils.reply_msg(message, 
        f"{actor_link} разблокировал(-а) {target_name}\nПричина: {reason or '-'}"
    )


@bot.on.message(CommandRule(names("banlist")))
async def cmd_banlist(message):
    if not await check_access(message, "tracker"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    rows = await database.list_banned_in_chat(chat_id)
    if not rows:
        await utils.reply_msg(message, "В этой беседе никто не заблокирован.")
        return
    lines = []
    for row in rows:
        lines.append(await utils.profile_link_auto(message.ctx_api, row["vk_id"]))
    await utils.reply_msg(message, "\n".join(lines))


@bot.on.message(CommandRule(names("quiet")))
async def cmd_quiet(message):
    if not await check_access(message, "tracker"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    currently = await database.is_quiet_mode(chat_id)
    await database.set_quiet_mode(chat_id, not currently)

    actor_link = await utils.profile_link_auto(message.ctx_api, message.from_id)
    action = "выключил" if currently else "включил"
    await utils.reply_msg(message, f"{actor_link} {action} режим тишины.")
