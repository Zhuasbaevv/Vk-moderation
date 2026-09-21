"""
Команды выдачи/снятия ролей.

Именные команды (глобально) и их "s"-версии (только в сетке беседы,
к которой привязан текущий чат - см. /setpull):

    /addld       -> Лидер            (кто может выдать: Старший следящий+)
    /saddld      -> Лидер, но только в сетке беседы
    /addsup      -> Следящий          (кто может выдать: Руководство+)
    /saddsup     -> Следящий, только в сетке беседы
    /addsensup   -> Старший следящий  (кто может выдать: Руководство+)
    /saddsensup  -> Старший следящий, только в сетке беседы
    /addadmin    -> Руководство       (кто может выдать: только Создатель)
    /saddadmin   -> Руководство, только в сетке беседы

Числовые команды (тот же порог доступа, что и у именных - в зависимости от
того, какая роль выдаётся под этим номером):
    /role [тег] [число]   -> глобально
    /srole [тег] [число]  -> только в сетке беседы
    1 - Старший состав, 2 - Лидер, 3 - Следящий, 4 - Старший следящий,
    5 - Руководство. Роль "Создатель" (6) командой не выдаётся.

Снятие роли (до какого порога роль снималась - такой же нужен доступ):
    /removerole, /rrole      -> глобально
    /sremoverole, /srrole    -> только в сетке беседы

Во всех случаях действует общее правило проекта: нельзя применить команду
к пользователю с ролью выше или равной своей (кроме Создателя).
"""
from .. import database, utils, chat_utils, config
from ..bot_instance import bot
from ..hierarchy import can_moderate, role_title, ROLE_ORDER
from ..permissions import check_access
from ..rules import CommandRule
from ..commands_meta import names

# Минимальная роль, которая нужна, чтобы выдать/снять роль такого-то уровня.
GRANT_THRESHOLD = {
    "senior_staff": "senior_tracker",
    "leader": "senior_tracker",
    "tracker": "leadership",
    "senior_tracker": "leadership",
    "leadership": "creator",
}


async def _do_assign(message, target_id: int, role_to_set: str, scope: str):
    threshold = GRANT_THRESHOLD.get(role_to_set)
    if threshold is None:
        await utils.reply_msg(message, "Эту роль нельзя выдать командой.")
        return
    if not await check_access(message, threshold):
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    actor_role = await database.get_effective_role(message.from_id, chat_id)
    target_role = await database.get_effective_role(target_id, chat_id)
    if not can_moderate(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    if scope == "global":
        await database.set_role(target_id, role_to_set)
        scope_text = ""
    else:
        pull_id = await database.get_pull_of_chat(chat_id)
        if pull_id is None:
            await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке (см. /setpull).")
            return
        await database.set_pull_role(target_id, pull_id, role_to_set)
        scope_text = " в сетке беседы"

    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    await utils.reply_msg(
        message, f"{target_link} назначен(а) на роль «{role_title(role_to_set)}»{scope_text}."
    )


async def _named_assign(message, role_to_set: str, scope: str):
    _, args = utils.parse_command(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return
    await _do_assign(message, target_id, role_to_set, scope)


async def _numbered_assign(message, scope: str):
    _, args = utils.parse_command(message.text)
    target_id, rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    number = utils.extract_first_int(rest)
    if number is None or not (1 <= number <= 6):
        await utils.reply_msg(
            message,
            "Использование: /role [тег] [число]\n"
            "1 - Старший состав, 2 - Лидер, 3 - Следящий, "
            "4 - Старший следящий, 5 - Руководство",
        )
        return
    if number == 6:
        await utils.reply_msg(message, "Роль «Создатель» нельзя выдать командой.")
        return

    role_to_set = ROLE_ORDER[number]
    await _do_assign(message, target_id, role_to_set, scope)


async def _remove_role(message, scope: str):
    _, args = utils.parse_command(message.text)
    target_id, _rest = await utils.resolve_target(message, args)
    if target_id is None:
        await utils.reply_msg(message, "Ответьте на сообщение пользователя или укажите тег.")
        return

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    pull_id = None

    if scope == "global":
        current_role = await database.get_role(target_id)
        if current_role == "user":
            await utils.reply_msg(message, "У пользователя нет роли.")
            return
    else:
        pull_id = await database.get_pull_of_chat(chat_id)
        if pull_id is None:
            await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке (см. /setpull).")
            return
        current_role = await database.get_pull_role(target_id, pull_id)
        if current_role is None:
            await utils.reply_msg(message, "У пользователя нет роли в этой сетке беседы.")
            return

    threshold = GRANT_THRESHOLD.get(current_role, "leadership")
    if not await check_access(message, threshold):
        return

    actor_role = await database.get_effective_role(message.from_id, chat_id)
    target_role = await database.get_effective_role(target_id, chat_id)
    if not can_moderate(actor_role, target_role):
        await utils.reply_msg(message, config.NO_ACCESS_TEXT)
        return

    if scope == "global":
        await database.set_role(target_id, "user")
        scope_text = ""
    else:
        await database.remove_pull_role(target_id, pull_id)
        scope_text = " в сетке беседы"

    target_link = await utils.profile_link_auto(message.ctx_api, target_id)
    await utils.reply_msg(message, f"У {target_link} снята роль{scope_text}.")


# ---------------------------------------------------------------------------
# Именные команды
# ---------------------------------------------------------------------------

@bot.on.message(CommandRule(names("addld")))
async def cmd_addld(message):
    await _named_assign(message, "leader", "global")


@bot.on.message(CommandRule(names("saddld")))
async def cmd_saddld(message):
    await _named_assign(message, "leader", "pull")


@bot.on.message(CommandRule(names("addsup")))
async def cmd_addsup(message):
    await _named_assign(message, "tracker", "global")


@bot.on.message(CommandRule(names("saddsup")))
async def cmd_saddsup(message):
    await _named_assign(message, "tracker", "pull")


@bot.on.message(CommandRule(names("addsensup")))
async def cmd_addsensup(message):
    await _named_assign(message, "senior_tracker", "global")


@bot.on.message(CommandRule(names("saddsensup")))
async def cmd_saddsensup(message):
    await _named_assign(message, "senior_tracker", "pull")


@bot.on.message(CommandRule(names("addadmin")))
async def cmd_addadmin(message):
    await _named_assign(message, "leadership", "global")


@bot.on.message(CommandRule(names("saddadmin")))
async def cmd_saddadmin(message):
    await _named_assign(message, "leadership", "pull")


# ---------------------------------------------------------------------------
# Числовые команды
# ---------------------------------------------------------------------------

@bot.on.message(CommandRule(names("role")))
async def cmd_role(message):
    await _numbered_assign(message, "global")


@bot.on.message(CommandRule(names("srole")))
async def cmd_srole(message):
    await _numbered_assign(message, "pull")


# ---------------------------------------------------------------------------
# Снятие роли
# ---------------------------------------------------------------------------

@bot.on.message(CommandRule(names("removerole")))
async def cmd_removerole(message):
    await _remove_role(message, "global")


@bot.on.message(CommandRule(names("rrole")))
async def cmd_rrole(message):
    await _remove_role(message, "global")


@bot.on.message(CommandRule(names("sremoverole")))
async def cmd_sremoverole(message):
    await _remove_role(message, "pull")


@bot.on.message(CommandRule(names("srrole")))
async def cmd_srrole(message):
    await _remove_role(message, "pull")
