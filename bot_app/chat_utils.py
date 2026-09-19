"""
Обёртки над VK API для операций с самой беседой: список участников,
название, исключение пользователя.
"""
from typing import List, Optional


def chat_id_from_peer(peer_id: int) -> Optional[int]:
    if peer_id and peer_id > 2000000000:
        return peer_id - 2000000000
    return None


def peer_from_chat_id(chat_id: int) -> int:
    return 2000000000 + chat_id


async def get_conversation_title(api, peer_id: int) -> str:
    try:
        result = await api.messages.get_conversations_by_id(peer_ids=[peer_id])
        items = getattr(result, "items", None) or result["items"]
        if items:
            item = items[0]
            chat_settings = getattr(item, "chat_settings", None)
            if chat_settings and getattr(chat_settings, "title", None):
                return chat_settings.title
    except Exception:
        pass
    return f"Беседа {chat_id_from_peer(peer_id)}"


async def get_online_member_ids(api, peer_id: int) -> List[int]:
    try:
        result = await api.messages.get_conversation_members(peer_id=peer_id)
        profiles = getattr(result, "profiles", None) or []
        online_ids = []
        for p in profiles:
            if getattr(p, "online", 0):
                online_ids.append(p.id)
        return online_ids
    except Exception:
        return []


async def get_all_member_ids(api, peer_id: int) -> List[int]:
    try:
        result = await api.messages.get_conversation_members(peer_id=peer_id)
        members = getattr(result, "items", None) or []
        return [m.member_id for m in members if m.member_id > 0]
    except Exception:
        return []


async def kick_member(api, peer_id: int, vk_id: int) -> bool:
    try:
        await api.messages.remove_chat_user(chat_id=chat_id_from_peer(peer_id), member_id=vk_id)
        return True
    except Exception:
        return False


async def broadcast(api, chat_ids, text: str, keyboard: str = None) -> None:
    """Отправляет одно и то же сообщение (опционально - с клавиатурой) в список бесед."""
    for cid in chat_ids:
        try:
            kwargs = {"peer_id": peer_from_chat_id(cid), "message": text, "random_id": 0}
            if keyboard is not None:
                kwargs["keyboard"] = keyboard
            await api.messages.send(**kwargs)
        except Exception:
            continue
