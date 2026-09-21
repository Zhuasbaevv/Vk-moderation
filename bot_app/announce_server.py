"""
Маленький HTTP-сервер (aiohttp), принимающий объявления от br-senior-bot
(сайт/Telegram-бот) и рассылающий их в нужные "инфо-беседы" (см.
handlers/info_chat_cmds.py, /addXinfo).

Запускается в ТОМ ЖЕ процессе, что и сам VK-бот (см. main.py), параллельно
с long poll - это не отдельный сервис, а ещё один слушающий сокет в том же
event loop.

Формат запроса:
    POST /internal/announce
    Header: X-Bridge-Secret: <совпадает с SITE_BRIDGE_SECRET>
    Body (JSON): {"orgs": ["Правительство", "СМИ"], "text": "..."}

Отвечает всем инфо-беседам организаций из "orgs" (без дублей, если несколько
организаций используют одну и ту же беседу). Организации без привязанной
инфо-беседы (ещё не вызывали /addXinfo) молча пропускаются.
"""
import json as _json

from aiohttp import web

from . import config, database
from .bot_instance import bot


async def _handle_announce(request: web.Request) -> web.Response:
    if not config.SITE_BRIDGE_SECRET:
        print("[announce_server] запрос отклонён - SITE_BRIDGE_SECRET не задан на этом сервисе")
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)
    if request.headers.get("X-Bridge-Secret", "") != config.SITE_BRIDGE_SECRET:
        print("[announce_server] запрос отклонён - секрет не совпадает с SITE_BRIDGE_SECRET этого сервиса")
        return web.json_response({"ok": False, "error": "forbidden"}, status=403)

    try:
        body = await request.json()
        orgs = body["orgs"]
        text = str(body["text"])
    except Exception as e:
        print(f"[announce_server] некорректное тело запроса: {e!r}")
        return web.json_response({"ok": False, "error": "bad_request"}, status=400)

    chat_ids = set()
    for org in orgs:
        chat_id = await database.get_info_chat(org)
        if chat_id is not None:
            chat_ids.add(chat_id)
        else:
            print(f'[announce_server] для организации "{org}" не привязана ни одна инфо-беседа')

    sent = 0
    for chat_id in chat_ids:
        try:
            await bot.api.messages.send(
                peer_id=2000000000 + chat_id, message=text, random_id=0
            )
            sent += 1
        except Exception as e:
            print(f"[announce_server] не смог отправить в чат {chat_id}: {e!r}")
            continue

    print(f"[announce_server] orgs={orgs} -> найдено бесед: {len(chat_ids)}, отправлено: {sent}")
    return web.json_response({"ok": True, "sent": sent, "matched_chats": len(chat_ids)})


def build_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/internal/announce", _handle_announce)
    return app


async def run_announce_server() -> None:
    """Запускать через asyncio.create_task(...) параллельно с bot.run_polling()."""
    app = build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.BRIDGE_PORT)
    await site.start()
    if config.SITE_BRIDGE_SECRET:
        print(f"[announce_server] слушаю порт {config.BRIDGE_PORT}, мост с сайтом настроен")
    else:
        print(f"[announce_server] слушаю порт {config.BRIDGE_PORT}, НО SITE_BRIDGE_SECRET не задан - все запросы будут отклонены")
