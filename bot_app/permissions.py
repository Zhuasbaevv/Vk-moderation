"""
Хелпер для проверки доступа к команде внутри хендлера.
"""
from . import database, config, chat_utils, utils
from .hierarchy import has_min_role


def _chat_id(message):
    peer_id = getattr(message, "peer_id", None)
    return chat_utils.chat_id_from_peer(peer_id) if peer_id else None


async def check_access(message, min_role: str) -> bool:
    """
    Возвращает True, если у автора сообщения есть доступ (роль >= min_role).
    Учитывает "эффективную" роль: глобальную ИЛИ роль, выданную отдельно в
    сетке бесед (/saddld, /srole и т.п.) для той сетки, к которой относится
    текущая беседа - берётся более старшая из двух.
    Если доступа нет - сама отвечает "❌️ Недоступно" и возвращает False.
    """
    await database.ensure_user(message.from_id)
    chat_id = _chat_id(message)
    role = await database.get_effective_role(message.from_id, chat_id)
    if has_min_role(role, min_role):
        return True
    await utils.reply_msg(message, config.NO_ACCESS_TEXT)
    return False


async def check_global_access(message, min_role: str) -> bool:
    """
    Как check_access, но игнорирует роль в сетке бесед - только глобальная
    роль пользователя. Используется для по-настоящему глобальных команд
    (/gban, /gkick, /gunban, /gzov, /setinfo), чтобы роль, выданная только
    в рамках одной сетки, не давала прав действовать сразу во всех беседах.
    """
    await database.ensure_user(message.from_id)
    role = await database.get_role(message.from_id)
    if has_min_role(role, min_role):
        return True
    await utils.reply_msg(message, config.NO_ACCESS_TEXT)
    return False
