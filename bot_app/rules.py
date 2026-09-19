"""
Правило (Rule) для vkbottle: команда считается совпавшей, если сообщение
начинается с одного из PREFIXES ("/", "!", "+", ".") и далее следует одно
из указанных имён/алиасов команды.
"""
from typing import List

from vkbottle.dispatch.rules.base import ABCRule
from vkbottle.bot import Message

from . import config


class CommandRule(ABCRule[Message]):
    def __init__(self, names: List[str]):
        self.names = {n.lower() for n in names}

    async def check(self, message: Message) -> bool:
        text = (message.text or "").strip()
        if not text:
            return False
        for prefix in config.PREFIXES:
            if text.startswith(prefix):
                rest = text[len(prefix):]
                cmd = rest.split(maxsplit=1)[0].lower() if rest.strip() else ""
                return cmd in self.names
        return False


class ChatMessageRule(ABCRule[Message]):
    """Совпадает с любым сообщением, отправленным в беседе (не в личке)."""

    async def check(self, message: Message) -> bool:
        return bool(message.peer_id and message.peer_id > 2000000000)


class ActionRule(ABCRule[Message]):
    """Совпадает со служебным сообщением определённого типа action (например, chat_invite_user)."""

    def __init__(self, action_type: str):
        self.action_type = action_type

    async def check(self, message: Message) -> bool:
        action = getattr(message, "action", None)
        return bool(action and getattr(action, "type", None) == self.action_type)
