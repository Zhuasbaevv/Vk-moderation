"""
Точка входа. Запуск: python main.py
Перед запуском заполните .env (см. .env.example) и установите зависимости:
    pip install -r requirements.txt
"""
import asyncio

from bot_app import database
from bot_app.bot_instance import bot
from bot_app import handlers  # noqa: F401  регистрирует все хендлеры
from bot_app.announce_server import run_announce_server


async def _startup():
    await database.init_db()
    print("База данных готова. Роли создателя назначены (если указаны в .env).")


async def _main_async():
    await _startup()
    print("Бот запущен, ожидаю сообщения...")
    # Long poll ВКонтакте и приём объявлений с сайта (см. announce_server.py)
    # работают в одном event loop как две параллельные задачи. bot.run_polling()
    # это асинхронный эквивалент bot.run_forever() (которым нельзя пользоваться
    # здесь напрямую - он сам оборачивает себя в asyncio.run(), что конфликтует
    # с уже запущенным циклом). Если в установленной версии vkbottle такого
    # метода нет - проверьте исходник run_forever() в самой библиотеке: там
    # почти наверняка будет asyncio.run(self.<имя_метода>()), и это имя нужно
    # подставить сюда вместо run_polling.
    await asyncio.gather(bot.run_polling(), run_announce_server())


def main():
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
