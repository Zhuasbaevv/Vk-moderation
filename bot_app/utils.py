"""
Вспомогательные функции: разбор команд, поиск цели (ответ/тег/ник),
форматирование упоминаний, работа со временем.
"""
import datetime
import json
import re
from typing import Optional, Tuple

from . import config

MENTION_RE = re.compile(r"\[id(\d+)\|[^\]]*\]")
ATID_RE = re.compile(r"@id(\d+)")
IDLINK_RE = re.compile(r"(?:https?://)?vk\.(?:com|ru)/id(\d+)")
SCREENLINK_RE = re.compile(r"(?:https?://)?vk\.(?:com|ru)/([A-Za-z0-9_.]+)")
ATSCREEN_RE = re.compile(r"@([A-Za-z0-9_.]+)")


def parse_command(text: str) -> Tuple[str, str]:
    """
    Возвращает (команда_без_префикса_в_нижнем_регистре, остаток_строки).
    Если текст не начинается ни с одного из префиксов - команда пустая.
    """
    if not text:
        return "", ""
    stripped = text.strip()
    for prefix in config.PREFIXES:
        if stripped.startswith(prefix):
            rest = stripped[len(prefix):]
            parts = rest.split(maxsplit=1)
            cmd = parts[0].lower() if parts else ""
            args = parts[1] if len(parts) > 1 else ""
            return cmd, args
    return "", ""


async def resolve_target(message, args: str) -> Tuple[Optional[int], str]:
    """
    Определяет ID пользователя-цели команды:
    1) Ответ на сообщение (reply)
    2) Упоминание вида [id123|Имя]
    3) @id123
    4) Ссылка vk.com/id123 или vk.ru/id123
    5) @screen_name или ссылка vk.com/screen_name (резолвится через API)

    Возвращает (vk_id или None, оставшийся текст без упоминания - обычно причина).
    """
    reply = getattr(message, "reply_message", None)
    if reply is not None:
        return reply.from_id, args.strip()

    m = MENTION_RE.search(args)
    if m:
        rest = MENTION_RE.sub("", args, count=1).strip()
        return int(m.group(1)), rest

    m = ATID_RE.search(args)
    if m:
        rest = ATID_RE.sub("", args, count=1).strip()
        return int(m.group(1)), rest

    m = IDLINK_RE.search(args)
    if m:
        rest = IDLINK_RE.sub("", args, count=1).strip()
        return int(m.group(1)), rest

    m = SCREENLINK_RE.search(args)
    if m:
        screen_name = m.group(1)
        rest = SCREENLINK_RE.sub("", args, count=1).strip()
        vk_id = await _resolve_screen_name(message, screen_name)
        if vk_id:
            return vk_id, rest

    m = ATSCREEN_RE.search(args)
    if m:
        screen_name = m.group(1)
        rest = ATSCREEN_RE.sub("", args, count=1).strip()
        vk_id = await _resolve_screen_name(message, screen_name)
        if vk_id:
            return vk_id, rest

    return None, args.strip()


async def _resolve_screen_name(message, screen_name: str) -> Optional[int]:
    try:
        result = await message.ctx_api.utils.resolve_screen_name(screen_name=screen_name)
        if result and getattr(result, "type", None) == "user":
            return result.object_id
    except Exception:
        pass
    return None


async def get_user_name(api, vk_id: int) -> str:
    try:
        users = await api.users.get(user_ids=[vk_id])
        if users:
            return f"{users[0].first_name} {users[0].last_name}"
    except Exception:
        pass
    return "Пользователь"


async def get_user_first_name(api, vk_id: int) -> str:
    try:
        users = await api.users.get(user_ids=[vk_id])
        if users:
            return users[0].first_name
    except Exception:
        pass
    return "Пользователь"


async def mention(api, vk_id: int) -> str:
    """Форматирует упоминание вида [id123|Имя Фамилия]."""
    name = await get_user_name(api, vk_id)
    return f"[id{vk_id}|{name}]"


def profile_link(vk_id: int, name: str) -> str:
    return f"[https://vk.com/id{vk_id}|{name}]"


def role_label_link(vk_id: int, label: str) -> str:
    """
    Ссылка на профиль с ФИКСИРОВАННОЙ подписью вместо реального имени -
    например [https://vk.com/id123|Администратором] или
    [https://vk.com/id123|Модератор]. Ссылка ведёт на настоящий профиль,
    но текст подписи не показывает имя/фамилию.
    """
    return f"[https://vk.com/id{vk_id}|{label}]"


async def profile_link_auto(api, vk_id: int) -> str:
    name = await get_user_name(api, vk_id)
    return profile_link(vk_id, name)


def extract_first_int(text: str) -> Optional[int]:
    """Ищет первое целое число в строке (используется и для минут мута, и для номера роли)."""
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def parse_duration_minutes(text: str) -> Optional[int]:
    return extract_first_int(text)


MSK_OFFSET = datetime.timedelta(hours=3)


def format_dt(dt: datetime.datetime) -> str:
    """dt ожидается наивным UTC (как хранится в БД/вычисляется через utcnow()).
    Показывается пользователю в московском времени."""
    msk = dt + MSK_OFFSET
    return msk.strftime("%Y-%m-%d %H:%M:%S МСК (UTC+3)")


def format_msk(iso_utc: Optional[str]) -> str:
    """Преобразует сохранённую в БД UTC-строку (isoformat) в московское время для показа."""
    if not iso_utc:
        return "—"
    try:
        dt = datetime.datetime.fromisoformat(iso_utc)
    except Exception:
        return iso_utc
    return format_dt(dt)


def days_since(iso_dt: str) -> int:
    try:
        dt = datetime.datetime.fromisoformat(iso_dt)
    except Exception:
        return 0
    return max((datetime.datetime.utcnow() - dt).days, 0)


async def reply_msg(message, text: str, keyboard: Optional[str] = None) -> None:
    """
    Отвечает НА сообщение пользователя - визуально как реплай (плашка-цитата
    сверху сообщения), а не просто отправляет новое сообщение в чат.
    keyboard - JSON-строка инлайн-клавиатуры (см. keyboards.py), опционально.

    ВАЖНО: параметр reply_to у messages.send работает только для личных
    диалогов с сообществом. Для беседы настоящий "ответ" делается через
    forward с флагом is_reply.
    """
    kwargs = {}
    if keyboard is not None:
        kwargs["keyboard"] = keyboard
    try:
        forward = json.dumps(
            {
                "peer_id": message.peer_id,
                "conversation_message_ids": [message.conversation_message_id],
                "is_reply": True,
            }
        )
        await message.answer(text, forward=forward, **kwargs)
    except Exception:
        await message.answer(text, **kwargs)
