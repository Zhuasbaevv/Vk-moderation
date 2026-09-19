"""
Конфигурация бота. Значения читаются из переменных окружения (.env).
"""
import os
from dotenv import load_dotenv

load_dotenv()

VK_TOKEN = os.getenv("VK_TOKEN", "")
VK_GROUP_ID = int(os.getenv("VK_GROUP_ID", "0") or 0)
DB_PATH = os.getenv("DB_PATH", "bot_data.db")

_creator_ids_raw = os.getenv("CREATOR_IDS", "")
CREATOR_IDS = [
    int(x.strip()) for x in _creator_ids_raw.split(",") if x.strip().isdigit()
]

# Префиксы команд: "/", "!", "+", "."
PREFIXES = ["/", "!", "+", "."]

# Текст, который бот присылает, если у пользователя нет доступа к команде
NO_ACCESS_TEXT = "❌️ Недоступно"

# ------------------------------------------------------------------
# Мост с сайтом/Telegram-ботом (br-senior-bot).
#
# Направление 1 (этот бот -> сайт): /stats подтягивает "Должность"/"Ранг"
# человека с сайта по его VK ID.
# Направление 2 (сайт -> этот бот): сайт/Telegram-бот шлёт сюда HTTP-запрос,
# когда кому-то назначили роль или выдали наказание/баллы - этот бот
# рассылает объявление в нужные "инфо-беседы" (см. handlers/info_chat_cmds.py).
#
# Оба направления не обязательны - если что-то из этого не настроено (пустая
# строка), соответствующая часть просто молча не работает, остальной бот
# продолжает работать как раньше.
# ------------------------------------------------------------------

# Базовый адрес веб-панели br-senior-bot, БЕЗ слэша на конце,
# например https://br-senior-bot-production.up.railway.app
SITE_API_URL = os.getenv("SITE_API_URL", "").rstrip("/")

# Общий секрет для обоих направлений моста - ОДИНАКОВОЕ значение должно быть
# прописано в переменных окружения и этого бота (SITE_BRIDGE_SECRET), и
# br-senior-bot (тоже SITE_BRIDGE_SECRET, см. его config.py).
SITE_BRIDGE_SECRET = os.getenv("SITE_BRIDGE_SECRET", "")

# Порт, на котором этот бот поднимает СВОЙ маленький HTTP-сервер для приёма
# объявлений от сайта (см. bot_app/announce_server.py). На Railway/Render
# подставляется через переменную PORT.
BRIDGE_PORT = int(os.getenv("PORT", os.getenv("BRIDGE_PORT", "8081")))

# Соответствие "короткая команда -> полное название организации" для
# /addXinfo (см. handlers/info_chat_cmds.py). ВАЖНО: названия организаций
# здесь должны БУКВА В БУКВУ совпадать с ALL_ORGS в config.py проекта
# br-senior-bot - это и есть общий "ключ", по которому сайт находит нужную
# инфо-беседу. Если там организацию переименуют/добавят новую - поправьте
# и здесь.
ORG_INFO_COMMANDS = {
    "ainfo": "Арзамасская ОПГ",
    "binfo": "Батыревская ОПГ",
    "linfo": "Лыткаринская ОПГ",
    "govinfo": "Правительство",
    "fsbinfo": "ФСБ",
    "umvdinfo": "УМВД",
    "gibddinfo": "ГИБДД",
    "armyinfo": "Армия",
    "hospinfo": "Больница",
    "fsininfo": "ФСИН",
    "sminfo": "СМИ",
}
