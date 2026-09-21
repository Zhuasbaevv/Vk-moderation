"""
HTTP-клиент для запроса профиля человека с сайта br-senior-bot по его VK ID
(используется в handlers/user_cmds.py, команда /stats - добавляет строки
"Должность"/"Ранг").

Если SITE_API_URL/SITE_BRIDGE_SECRET не заданы, или сайт не отвечает -
функция просто возвращает None, а /stats показывает статистику без этих
строк (как и раньше) - мост не обязателен для работы бота.
"""
import aiohttp

from . import config

_TIMEOUT = aiohttp.ClientTimeout(total=5)


async def fetch_site_profile(vk_id: int) -> dict | None:
    """
    Возвращает {"position": "<Должность>", "rank": "<Ранг или None>",
    "nickname": "<NickName или None>"} или None, если мост не настроен,
    сайт недоступен, либо человек с таким VK ID на сайте не найден.
    """
    if not config.SITE_API_URL or not config.SITE_BRIDGE_SECRET:
        return None

    url = f"{config.SITE_API_URL}/internal/vk-profile"
    headers = {"X-Bridge-Secret": config.SITE_BRIDGE_SECRET}
    params = {"vk_id": str(vk_id)}

    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.get(url, headers=headers, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
    except Exception:
        return None

    if not data.get("found"):
        return None
    return {
        "position": data.get("position") or None,
        "rank": data.get("rank") or None,
        "org": data.get("org") or None,
        "nickname": data.get("nickname") or None,
    }
