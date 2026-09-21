"""
Команды привязки "инфо-бесед" по организациям - куда бот будет присылать
объявления о назначениях/наказаниях, прилетающие с сайта br-senior-bot (см.
bot_app/announce_server.py).

ВАЖНО: эти команды намеренно НЕ добавлены ни в commands_meta.ALIASES, ни в
HELP_SECTIONS - поэтому не показываются ни в /help, ни в /alt. Доступ - только
Создателю (роль "creator"), напрямую через check_access, а не через общий
порог команд.

РЕАЛИЗАЦИЯ: один хендлер на ВСЕ команды /addXinfo сразу (а не 11 отдельных,
зарегистрированных динамически в цикле через bot.on.message(...)(handler) -
такой вариант в связке с этой версией vkbottle молча не срабатывал ни на одну
из команд). Внутри хендлера по самому тексту команды определяем, какая
именно организация имелась в виду - надёжный способ, не зависящий от того,
поддерживает ли конкретная версия vkbottle программную регистрацию
декораторов вне @-синтаксиса.
"""
from .. import database, config, utils, chat_utils
from ..bot_instance import bot
from ..permissions import check_access
from ..rules import CommandRule

# {"addainfo": "Арзамасская ОПГ", "addbinfo": "Батыревская ОПГ", ...}
_ADD_COMMANDS = {f"add{suffix}": org for suffix, org in config.ORG_INFO_COMMANDS.items()}


def _extract_command(message) -> str:
    text = (message.text or "").strip()
    for prefix in config.PREFIXES:
        if text.startswith(prefix):
            rest = text[len(prefix):]
            return rest.split(maxsplit=1)[0].lower() if rest.strip() else ""
    return ""


@bot.on.message(CommandRule(list(_ADD_COMMANDS.keys())))
async def cmd_add_org_info(message):
    if not await check_access(message, "creator"):
        return
    cmd = _extract_command(message)
    org_name = _ADD_COMMANDS.get(cmd)
    if org_name is None:
        return  # теоретически недостижимо - CommandRule уже отфильтровал по этим же именам

    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    if chat_id is None:
        await utils.reply_msg(message, "Эту команду нужно вызывать в беседе, а не в личных сообщениях.")
        return
    title = await chat_utils.get_conversation_title(message.ctx_api, message.peer_id)
    await database.set_info_chat(org_name, chat_id, title)
    await utils.reply_msg(
        message, f'Эта беседа [{title}] назначена инфо-беседой организации "{org_name}".'
    )


@bot.on.message(CommandRule(["delinfo"]))
async def cmd_delinfo(message):
    """Снимает привязку ТЕКУЩЕЙ беседы как инфо-беседы (для любой организации)."""
    if not await check_access(message, "creator"):
        return
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    if chat_id is None:
        await utils.reply_msg(message, "Эту команду нужно вызывать в беседе, а не в личных сообщениях.")
        return
    removed_org = await database.remove_info_chat_by_chat_id(chat_id)
    if removed_org is None:
        await utils.reply_msg(message, "Эта беседа не была ничьей инфо-беседой.")
        return
    await utils.reply_msg(message, f'Эта беседа больше не инфо-беседа организации "{removed_org}".')
