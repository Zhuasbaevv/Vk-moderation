"""
Логирование сообщений (см. /go, /logs в creator_cmds.py).

Формат заголовка лога:
    1. Беседа: <название>
    2. NickName: <ник или тег ВК>
    3. Время: <время в МСК>
    4. Номер сообщ: #N
    5. Ответил на сообщение: #M   (только если это ответ)

Если сообщение отредактировано - в лог уходит ОТДЕЛЬНАЯ запись с пометкой
"✏️ Сообщение отредактировано" и тем же номером #N (номер не меняется -
строка в log_message_index уже существует для этого conversation_message_id).

Само сообщение (текст/стикеры/фото и т.п.) не пересобирается вручную -
бот пересылает ОРИГИНАЛ через forward, поэтому вложения приходят как есть.

ВАЖНО ПРО СОВМЕСТИМОСТЬ И НАСТРОЙКИ VK:
1) Как и callbacks.py, обработчик редактирования подписан через
   bot.on.raw_event(...) БЕЗ параметра rules= (в установленной версии
   vkbottle raw_event его не поддерживает). Тип события передаётся как
   обычная строка "message_edit", а не через GroupEventType.MESSAGE_EDIT -
   так надёжнее: если в установленной версии vkbottle нет такого имени в
   enum, код всё равно не упадёт при импорте (raw_event сравнивает событие
   по значению строки, а не по объекту enum).
2) ГЛАВНАЯ ПРИЧИНА, по которой бот может "не видеть" редактирование - VK
   по умолчанию НЕ шлёт событие message_edit, пока оно явно не включено в
   настройках сообщества: Управление сообществом -> Работа с API ->
   Long Poll API (или Callback API) -> список событий -> отметьте
   "Редактирование сообщения" отдельным чекбоксом (это НЕ то же самое, что
   "Новое сообщение"). Без этой галочки событие никогда не придёт, даже
   если весь код написан правильно.
"""
import datetime
import json

from vkbottle.bot import Message

from .. import database, utils, chat_utils
from ..bot_instance import bot
from ..rules import ChatMessageRule

_MESSAGE_EDIT_EVENT = "message_edit"


async def _build_header(
    api, peer_id: int, vk_id: int, number: int, reply_number: int = None, is_edit: bool = False
) -> str:
    chat_title = await chat_utils.get_conversation_title(api, peer_id)
    nickname = await database.get_nickname(vk_id)
    who = nickname if nickname else await utils.profile_link_auto(api, vk_id)
    lines = []
    if is_edit:
        lines.append("✏️ Сообщение отредактировано")
    lines += [
        f"1. Беседа: {chat_title}",
        f"2. NickName: {who}",
        f"3. Время: {utils.format_dt(datetime.datetime.utcnow())}",
        f"4. Номер сообщ: #{number}",
    ]
    if reply_number is not None:
        lines.append(f"5. Ответил на сообщение: #{reply_number}")
    return "\n".join(lines)


async def _forward_to_log(api, log_chat_id: int, source_peer_id: int, cmid: int, header: str) -> None:
    forward = json.dumps({
        "peer_id": source_peer_id,
        "conversation_message_ids": [cmid],
    })
    try:
        await api.messages.send(
            peer_id=chat_utils.peer_from_chat_id(log_chat_id),
            message=header,
            forward=forward,
            random_id=0,
        )
    except Exception:
        pass


async def _log_message(message, is_edit: bool = False) -> None:
    chat_id = chat_utils.chat_id_from_peer(message.peer_id)
    if chat_id is None:
        return
    if not await database.is_logging_enabled(chat_id):
        return
    log_chat_id = await database.get_global_log_chat()
    if log_chat_id is None:
        return

    number = await database.get_or_assign_log_number(chat_id, message.conversation_message_id)

    reply_number = None
    reply = getattr(message, "reply_message", None)
    if reply is not None:
        reply_number = await database.get_log_number(chat_id, reply.conversation_message_id)

    header = await _build_header(
        message.ctx_api, message.peer_id, message.from_id, number, reply_number, is_edit
    )
    await _forward_to_log(
        message.ctx_api, log_chat_id, message.peer_id, message.conversation_message_id, header
    )


@bot.on.message(ChatMessageRule(), blocking=False)
async def on_message_for_logging(message: Message) -> None:
    await _log_message(message, is_edit=False)


@bot.on.raw_event(_MESSAGE_EDIT_EVENT, dataclass=Message)
async def on_message_edit_for_logging(message: Message) -> None:
    # Номер (#N) не меняется - get_or_assign_log_number найдёт уже
    # существующую запись для этого conversation_message_id.
    await _log_message(message, is_edit=True)
