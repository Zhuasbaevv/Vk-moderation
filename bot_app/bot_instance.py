"""
Единственный экземпляр Bot из vkbottle, используемый во всех хендлерах.
Вынесен в отдельный модуль, чтобы избежать циклических импортов между
main.py и bot_app/handlers/*.py.
"""
from vkbottle.bot import Bot

from . import config

bot = Bot(token=config.VK_TOKEN)
