"""
Сборка inline-клавиатур VK (callback-кнопки под сообщением).

Формат клавиатуры - обычный JSON VK Bots API:
    {"inline": true, "buttons": [[{"action": {...}, "color": "..."}]]}

Кнопка типа "callback" при нажатии присылает боту событие message_event
(см. handlers/callbacks.py) вместо отправки текста в чат - это и есть
"инлайн-кнопки" в понимании VK.
"""
import json

PAGE_SIZE = 50


def _button(label: str, payload: dict, color: str = "secondary") -> dict:
    return {
        "action": {
            "type": "callback",
            "label": label,
            "payload": json.dumps(payload, ensure_ascii=False),
        },
        "color": color,
    }


def _build(rows) -> str:
    return json.dumps({"inline": True, "buttons": rows}, ensure_ascii=False)


def empty_keyboard() -> str:
    """Пустая клавиатура - используется, чтобы убрать кнопки после использования."""
    return _build([])


def nick_keyboard(view: str, page: int, total_pages: int) -> str:
    """
    view: "nlist" (с никами) или "nonick" (без ников).
    Ряд кнопок: [◀ Пред. страница] [Без ников / С никами] [След. страница ▶].
    Кнопки "пред/след" показываются только если есть куда листать.
    """
    row = []
    if page > 1:
        row.append(_button(f"◀️ Стр. {page - 1}", {"cmd": view, "page": page - 1}))

    other_view = "nonick" if view == "nlist" else "nlist"
    other_label = "Без ников" if view == "nlist" else "С никами"
    row.append(_button(other_label, {"cmd": other_view, "page": 1}))

    if page < total_pages:
        row.append(_button(f"Стр. {page + 1} ▶️", {"cmd": view, "page": page + 1}))

    return _build([row])


def punishment_keyboard(action: str, target_id: int, **extra) -> str:
    """
    Кнопка-антоним для конкретного наказания.
    action: "unmute" | "unban" | "unwarn" | "sunban" | "gunban"
    extra: доп. данные, нужные обработчику (chat_id и т.п.) - кладутся в payload как есть.
    """
    labels = {
        "unmute": "🔓 Снять мут",
        "unban": "🔓 Снять бан",
        "unwarn": "🔓 Снять варн",
        "sunban": "🔓 Снять бан в сетке",
        "gunban": "🔓 Снять глобал-бан",
    }
    payload = {"cmd": action, "target": target_id}
    payload.update(extra)
    return _build([[_button(labels.get(action, action), payload, color="positive")]])
