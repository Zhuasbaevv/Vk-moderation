"""
Обработка нажатий на inline-кнопки (VK Bots API: событие message_event).

ВАЖНО ПРО СОВМЕСТИМОСТЬ: это единственное место в проекте, где используется
не Message, а другой тип апдейта (MessageEvent). Сами методы VK API
(messages.send_message_event_answer, messages.edit) - часть официального
протокола и не меняются от версии к версии.

Регистрация через bot.on.raw_event(...) в установленной версии vkbottle НЕ
принимает параметр rules= (это только для bot.on.message()) - поэтому здесь
один-единственный обработчик на GroupEventType.MESSAGE_EVENT, а маршрутизация
по конкретной кнопке (payload["cmd"]) делается вручную внутри него через
словарь _HANDLERS. Если в вашей версии vkbottle иначе называется dataclass
для этого события - поменяйте только импорт MessageEvent ниже, остальной
код трогать не нужно.
"""
import json

from vkbottle import GroupEventType
from vkbottle.bot import MessageEvent

from .. import database, utils, chat_utils, config
from ..bot_instance import bot
from ..hierarchy import has_min_role
from .nick_list_cmds import render_nick_page
from ..keyboards import nick_keyboard, empty_keyboard


def _get_payload(event) -> dict:
    payload = getattr(event, "payload", None)
    if payload is None:
        return {}
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            return {}
    return payload


async def _answer(event, snackbar: str = None) -> None:
    """Закрывает "часики" на кнопке; snackbar - всплывающее сообщение (например, отказ в доступе)."""
    kwargs = {"event_id": event.event_id, "user_id": event.user_id, "peer_id": event.peer_id}
    if snackbar:
        kwargs["event_data"] = json.dumps({"type": "show_snackbar", "text": snackbar})
    try:
        await event.ctx_api.messages.send_message_event_answer(**kwargs)
    except Exception:
        pass


async def _deny(event) -> None:
    await _answer(event, config.NO_ACCESS_TEXT)


async def _edit(event, text: str, keyboard: str = None) -> None:
    kwargs = {
        "peer_id": event.peer_id,
        "conversation_message_id": event.conversation_message_id,
        "message": text,
    }
    if keyboard is not None:
        kwargs["keyboard"] = keyboard
    try:
        await event.ctx_api.messages.edit(**kwargs)
    except Exception:
        pass


async def _actor_role(event) -> str:
    chat_id = chat_utils.chat_id_from_peer(event.peer_id)
    return await database.get_effective_role(event.user_id, chat_id)


# ---------------------------------------------------------------------------
# Обработчики конкретных кнопок (по значению payload["cmd"])
# ---------------------------------------------------------------------------

async def _handle_nick_page(event, payload) -> None:
    role = await _actor_role(event)
    if not has_min_role(role, "leader"):
        await _deny(event)
        return

    view = payload.get("cmd")
    page = int(payload.get("page", 1))

    text, page, total_pages = await render_nick_page(event.ctx_api, view, page)
    kb = nick_keyboard(view, page, total_pages)

    await _answer(event)
    await _edit(event, text, kb)


async def _handle_unmute(event, payload) -> None:
    role = await _actor_role(event)
    if not has_min_role(role, "leader"):
        await _deny(event)
        return

    target_id = payload["target"]
    chat_id = payload["chat_id"]

    await database.remove_mute(target_id, chat_id)

    actor_link = await utils.profile_link_auto(event.ctx_api, event.user_id)
    target_link = await utils.profile_link_auto(event.ctx_api, target_id)
    await _answer(event, "Мут снят")
    await _edit(event, f"{actor_link} снял(-а) мут с {target_link} ✅", empty_keyboard())


async def _handle_unban(event, payload) -> None:
    role = await _actor_role(event)
    if not has_min_role(role, "tracker"):
        await _deny(event)
        return

    target_id = payload["target"]
    chat_id = payload["chat_id"]

    removed = await database.remove_chat_ban(target_id, chat_id)
    if not removed:
        await _answer(event, "Уже разблокирован(а)")
        return

    actor_link = await utils.profile_link_auto(event.ctx_api, event.user_id)
    target_link = await utils.profile_link_auto(event.ctx_api, target_id)
    await _answer(event, "Бан снят")
    await _edit(event, f"{actor_link} разблокировал(-а) {target_link} ✅", empty_keyboard())


async def _handle_unwarn(event, payload) -> None:
    role = await _actor_role(event)
    if not has_min_role(role, "leader"):
        await _deny(event)
        return

    target_id = payload["target"]

    removed = await database.remove_latest_warn(target_id, event.user_id)
    if removed is None:
        await _answer(event, "Уже нет активных варнов")
        return

    remaining = await database.count_active_warns(target_id)
    actor_link = await utils.profile_link_auto(event.ctx_api, event.user_id)
    target_link = await utils.profile_link_auto(event.ctx_api, target_id)
    await _answer(event, "Варн снят")
    await _edit(
        event,
        f"{actor_link} снял(-а) предупреждение с {target_link} ✅\n"
        f"Осталось активных: {remaining}",
        empty_keyboard(),
    )


async def _handle_sunban(event, payload) -> None:
    role = await _actor_role(event)
    if not has_min_role(role, "senior_tracker"):
        await _deny(event)
        return

    target_id = payload["target"]
    pull_id = payload["pull_id"]

    chain = await database.get_pull_chain(pull_id)
    removed_any = False
    for pid in chain:
        removed = await database.remove_pull_ban(target_id, pid)
        removed_any = removed_any or removed

    if not removed_any:
        await _answer(event, "Уже разблокирован(а)")
        return

    actor_link = await utils.profile_link_auto(event.ctx_api, event.user_id)
    target_link = await utils.profile_link_auto(event.ctx_api, target_id)
    await _answer(event, "Бан в сетке снят")
    await _edit(
        event, f"{actor_link} разблокировал(-а) {target_link} в сетке беседы ✅", empty_keyboard()
    )


async def _handle_gunban(event, payload) -> None:
    # Глобальные права - только глобальная роль (см. permissions.check_global_access).
    global_role = await database.get_role(event.user_id)
    if not has_min_role(global_role, "leadership"):
        await _deny(event)
        return

    target_id = payload["target"]

    removed = await database.remove_global_ban(target_id)
    if not removed:
        await _answer(event, "Уже разблокирован(а)")
        return

    actor_link = await utils.profile_link_auto(event.ctx_api, event.user_id)
    target_link = await utils.profile_link_auto(event.ctx_api, target_id)
    await _answer(event, "Глобал-бан снят")
    await _edit(
        event, f"{actor_link} разблокировал(-а) во всех беседах {target_link} ✅", empty_keyboard()
    )


_HANDLERS = {
    "nlist": _handle_nick_page,
    "nonick": _handle_nick_page,
    "unmute": _handle_unmute,
    "unban": _handle_unban,
    "unwarn": _handle_unwarn,
    "sunban": _handle_sunban,
    "gunban": _handle_gunban,
}


@bot.on.raw_event(GroupEventType.MESSAGE_EVENT, dataclass=MessageEvent)
async def on_message_event(event: MessageEvent) -> None:
    payload = _get_payload(event)
    cmd = payload.get("cmd")
    handler = _HANDLERS.get(cmd)
    if handler is None:
        return
    try:
        await handler(event, payload)
    except Exception:
        await _answer(event, "Произошла ошибка, попробуйте ещё раз.")
