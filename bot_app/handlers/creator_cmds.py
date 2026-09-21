from .. import database, utils, chat_utils
from ..bot_instance import bot
from ..permissions import check_access
from ..rules import CommandRule
from ..commands_meta import names


@bot.on.message(CommandRule(names("setpull")))
async def cmd_setpull(message):
    if not await check_access(message, "creator"):
        return
    _, args = utils.parse_command(message.text)
    if not args.strip().isdigit():
        await utils.reply_msg(message, "Использование: /setpull [номер сетки], например /setpull 1")
        return
    pull_id = int(args.strip())
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    title = await chat_utils.get_conversation_title(message.ctx_api, message.peer_id)
    await database.attach_chat_to_pull(chat_id, pull_id)
    await utils.reply_msg(message, f'Беседа [{title}] добавлена в сетку бесед "{pull_id}".')


@bot.on.message(CommandRule(names("setdirection")))
async def cmd_setdirection(message):
    """
    Привязывает СЕТКУ ТЕКУЩЕЙ беседы (уже назначенную через /setpull) как
    дочернюю к сетке НАПРАВЛЕНИЯ. После этого кик/бан/зов, выполненные в
    любой беседе организации, дополнительно затронут беседу(-ы) направления
    (и, если направление само привязано к холдингу через /setholding - то и
    беседу всех организаций).

    Пример: в чате "Л-ОПГ" уже сделали /setpull 101 (сетка организации).
    Заходим туда же и пишем /setdirection 10, где 10 - номер сетки
    направления "Криминальные" (у неё, в свою очередь, есть своя беседа,
    привязанная через /setpull 10 в чате направления).
    """
    if not await check_access(message, "creator"):
        return
    _, args = utils.parse_command(message.text)
    if not args.strip().isdigit():
        await utils.reply_msg(
            message,
            "Использование: /setdirection [номер сетки направления]\n"
            "(сначала в этой беседе должна быть выполнена /setpull)",
        )
        return
    direction_pull_id = int(args.strip())

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    own_pull_id = await database.get_pull_of_chat(chat_id)
    if own_pull_id is None:
        await utils.reply_msg(
            message, "Эта беседа ещё не привязана к сетке. Сначала выполните /setpull."
        )
        return
    if own_pull_id == direction_pull_id:
        await utils.reply_msg(message, "Сетка не может быть направлением сама для себя.")
        return

    await database.set_pull_parent(own_pull_id, direction_pull_id)
    await utils.reply_msg(
        message,
        f'Сетка "{own_pull_id}" привязана к сетке направления "{direction_pull_id}".',
    )


@bot.on.message(CommandRule(names("setholding")))
async def cmd_setholding(message):
    """
    То же самое, что /setdirection, но для верхнего уровня: привязывает
    сетку ТЕКУЩЕЙ беседы (обычно это уже сетка направления) как дочернюю к
    сетке "все организации" (холдинг).

    Пример: в чате направления "Криминальные" уже сделали /setpull 10.
    Заходим туда же и пишем /setholding 1, где 1 - номер сетки "Все
    организации" (у неё есть своя общая беседа, привязанная через
    /setpull 1 в самой этой беседе).
    """
    if not await check_access(message, "creator"):
        return
    _, args = utils.parse_command(message.text)
    if not args.strip().isdigit():
        await utils.reply_msg(
            message,
            "Использование: /setholding [номер сетки всех организаций]\n"
            "(сначала в этой беседе должна быть выполнена /setpull)",
        )
        return
    holding_pull_id = int(args.strip())

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    own_pull_id = await database.get_pull_of_chat(chat_id)
    if own_pull_id is None:
        await utils.reply_msg(
            message, "Эта беседа ещё не привязана к сетке. Сначала выполните /setpull."
        )
        return
    if own_pull_id == holding_pull_id:
        await utils.reply_msg(message, "Сетка не может быть холдингом сама для себя.")
        return

    await database.set_pull_parent(own_pull_id, holding_pull_id)
    await utils.reply_msg(
        message,
        f'Сетка "{own_pull_id}" привязана к сетке всех организаций "{holding_pull_id}".',
    )


@bot.on.message(CommandRule(names("delsetdirection")))
async def cmd_delsetdirection(message):
    """Отвязывает сетку текущей беседы от родительской сетки направления."""
    if not await check_access(message, "creator"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    own_pull_id = await database.get_pull_of_chat(chat_id)
    if own_pull_id is None:
        await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке.")
        return
    parent = await database.get_pull_parent(own_pull_id)
    if parent is None:
        await utils.reply_msg(message, "У этой сетки нет родительской сетки направления.")
        return
    await database.remove_pull_parent(own_pull_id)
    await utils.reply_msg(
        message, f'Сетка "{own_pull_id}" отвязана от сетки направления "{parent}".'
    )


@bot.on.message(CommandRule(names("delsetholding")))
async def cmd_delsetholding(message):
    """Отвязывает сетку текущей беседы от родительской сетки холдинга."""
    if not await check_access(message, "creator"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    own_pull_id = await database.get_pull_of_chat(chat_id)
    if own_pull_id is None:
        await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке.")
        return
    parent = await database.get_pull_parent(own_pull_id)
    if parent is None:
        await utils.reply_msg(message, "У этой сетки нет родительской сетки холдинга.")
        return
    await database.remove_pull_parent(own_pull_id)
    await utils.reply_msg(
        message, f'Сетка "{own_pull_id}" отвязана от сетки всех организаций "{parent}".'
    )


@bot.on.message(CommandRule(names("delpull")))
async def cmd_delpull(message):
    if not await check_access(message, "creator"):
        return
    _, args = utils.parse_command(message.text)
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    title = await chat_utils.get_conversation_title(message.ctx_api, message.peer_id)

    pull_id = None
    if args.strip().isdigit():
        pull_id = int(args.strip())
    else:
        pull_id = await database.get_pull_of_chat(chat_id)

    if pull_id is None:
        await utils.reply_msg(message, "Эта беседа не привязана ни к одной сетке.")
        return

    removed = await database.detach_chat_from_pull(chat_id, pull_id)
    if not removed:
        await utils.reply_msg(message, f'Беседа не состояла в сетке "{pull_id}".')
        return
    await utils.reply_msg(message, f'Беседа [{title}] удалена из сетки беседы "{pull_id}".')


@bot.on.message(CommandRule(names("global")))
async def cmd_global(message):
    if not await check_access(message, "creator"):
        return
    _, args = utils.parse_command(message.text)
    group_name = args.strip() or "1"
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    title = await chat_utils.get_conversation_title(message.ctx_api, message.peer_id)
    await database.add_global_chat(chat_id, group_name)
    await utils.reply_msg(message, f'Беседа [{title}] успешно добавлена в глобальные беседы "{group_name}".')


@bot.on.message(CommandRule(names("delglobal")))
async def cmd_delglobal(message):
    if not await check_access(message, "creator"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    title = await chat_utils.get_conversation_title(message.ctx_api, message.peer_id)
    group_name = await database.get_global_group_name(chat_id) or "1"
    removed = await database.remove_global_chat(chat_id)
    if not removed:
        await utils.reply_msg(message, "Эта беседа не состоит в глобальных беседах.")
        return
    await utils.reply_msg(message, f'Беседа [{title}] успешно удалена из списка глобальных бесед "{group_name}".')


@bot.on.message(CommandRule(names("nickname")))
async def cmd_nickname(message):
    if not await check_access(message, "creator"):
        return
    _, title = utils.parse_command(message.text)
    if not title.strip():
        await utils.reply_msg(message, "Использование: /nickname [Название беседы]")
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    try:
        await message.ctx_api.messages.edit_chat(chat_id=chat_id, title=title.strip())
    except Exception:
        pass
    await database.set_chat_title(chat_id, title.strip())
    await utils.reply_msg(message, "Успешно")


@bot.on.message(CommandRule(names("go")))
async def cmd_go(message):
    """
    Включает/выключает логирование ЭТОЙ беседы (повторный вызов - выключает,
    как /quiet). Сообщения из неё будут пересылаться в беседу, назначенную
    через /logs. Если /logs ещё не была вызвана нигде - предупреждаем.
    """
    if not await check_access(message, "creator"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)

    if await database.is_logging_enabled(chat_id):
        await database.disable_logging(chat_id)
        await utils.reply_msg(message, "Логирование этой беседы выключено.")
        return

    if await database.get_global_log_chat() is None:
        await utils.reply_msg(
            message,
            "Логирование включено, но беседа-приёмник логов ещё не назначена.\n"
            "Выполните /logs в той беседе, куда должны приходить логи.",
        )
    else:
        await utils.reply_msg(message, "Логирование этой беседы включено.")

    await database.enable_logging(chat_id)


@bot.on.message(CommandRule(names("logs")))
async def cmd_logs(message):
    """Назначает ЭТУ беседу единственным приёмником логов (см. /go)."""
    if not await check_access(message, "creator"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    await database.set_global_log_chat(chat_id)
    await utils.reply_msg(message, "Эта беседа назначена для отправки логов.")
