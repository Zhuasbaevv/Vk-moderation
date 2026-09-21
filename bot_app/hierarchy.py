"""
Иерархия ролей бота (от младшей к старшей).

user            -> Пользователь (участник без роли)
senior_staff    -> Старший состав
leader          -> Лидер
tracker         -> Следящий
senior_tracker  -> Старший следящий
leadership      -> Руководство
creator         -> Создатель
"""

ROLE_ORDER = [
    "user",
    "senior_staff",
    "leader",
    "tracker",
    "senior_tracker",
    "leadership",
    "creator",
]

ROLE_TITLES = {
    "user": "Пользователь",
    "senior_staff": "Старший состав",
    "leader": "Лидер",
    "tracker": "Следящий",
    "senior_tracker": "Старший следящий",
    "leadership": "Руководство",
    "creator": "Создатель",
}

# Обратный маппинг: русское название -> ключ роли (используется, например, в /addrole)
TITLE_TO_ROLE = {v.lower(): k for k, v in ROLE_TITLES.items()}


def role_level(role: str) -> int:
    """Числовой уровень роли. Неизвестная роль = уровень 'user'."""
    try:
        return ROLE_ORDER.index(role)
    except ValueError:
        return 0


def role_title(role: str) -> str:
    return ROLE_TITLES.get(role, ROLE_TITLES["user"])


def has_min_role(role: str, min_role: str) -> bool:
    """Есть ли у роли доступ уровня min_role и выше."""
    return role_level(role) >= role_level(min_role)


def can_moderate(actor_role: str, target_role: str) -> bool:
    """
    Может ли actor_role применить наказание/действие к target_role.

    Правило проекта:
    - Человек не может выдавать муты/баны/кики людям, чья роль выше
      или равна его собственной.
    - ТОЛЬКО Создатель может взаимодействовать сам с собой и со всеми
      остальными вне зависимости от роли.
    """
    if actor_role == "creator":
        return True
    return role_level(actor_role) > role_level(target_role)


def can_view_stats(actor_role: str, target_role: str) -> bool:
    """
    Человек может смотреть статистику людей равных ему по рангу или ниже,
    но не может смотреть статистику людей выше.
    """
    if actor_role == "creator":
        return True
    return role_level(actor_role) >= role_level(target_role)
