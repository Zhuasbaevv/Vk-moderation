"""
Этот хендлер отрабатывает на КАЖДОЕ сообщение в беседе (blocking=False, то
есть не мешает остальным хендлерам с командами), и:
  1) обновляет статистику сообщений и "последний онлайн";
  2) если автор в муте в этой беседе - удаляет сообщение;
  3) если в беседе включён режим тишины - удаляет сообщения "Старшего состава".

ВАЖНО: поскольку blocking=False, хендлеры команд ниже по файлу всё равно
получат это же сообщение и ответят на команду, даже если она была удалена
здесь как "сообщение от замученного". Для полной строгости (не отвечать на
команды от замученных) можно дополнительно вызывать database.is_muted(...)
в начале каждого хендлера команд - выбор оставлен как точка расширения.
"""
from .. import database
from ..bot_instance import bot
from ..rules import ChatMessageRule


def _chat_id_from_peer(peer_id: int):
    if peer_id and peer_id > 2000000000:
        return peer_id - 2000000000
    return None


@bot.on.message(ChatMessageRule(), blocking=False)
async def guard_and_stats(message):
    chat_id = _chat_id_from_peer(message.peer_id)
    if chat_id is None:
        return

    await database.touch_online(message.from_id)
    await database.bump_message_stat(message.from_id, chat_id)
    await database.ensure_known_chat(chat_id)

    if await database.is_muted(message.from_id, chat_id):
        await _try_delete(message)
        return

    if await database.is_quiet_mode(chat_id):
        role = await database.get_role(message.from_id)
        if role == "senior_staff":
            await _try_delete(message)
            return


async def _try_delete(message):
    try:
        await message.ctx_api.messages.delete(
            conversation_message_ids=[message.conversation_message_id],
            peer_id=message.peer_id,
            delete_for_all=1,
        )
    except Exception:
        # Нет прав администратора беседы или сообщение уже удалено - игнорируем.
        pass
