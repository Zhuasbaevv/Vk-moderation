"""
Слой работы с базой данных (SQLite).

Для простоты используется синхронный sqlite3 с одним соединением и
блокировкой (threading.Lock), а вызовы из асинхронного кода оборачиваются
через loop.run_in_executor. Этого достаточно для бота, обслуживающего
десятки-сотни бесед; при росте нагрузки можно перейти на aiosqlite/Postgres,
не меняя публичный интерфейс функций ниже.
"""
import asyncio
import datetime
import sqlite3
import threading
from typing import Optional, List, Tuple

from . import config
from .hierarchy import role_level

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
    return _conn


def _execute(query: str, params: tuple = ()) -> sqlite3.Cursor:
    with _lock:
        conn = _get_conn()
        cur = conn.execute(query, params)
        conn.commit()
        return cur


def _fetchone(query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    with _lock:
        conn = _get_conn()
        cur = conn.execute(query, params)
        return cur.fetchone()


def _fetchall(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    with _lock:
        conn = _get_conn()
        cur = conn.execute(query, params)
        return cur.fetchall()


async def run(query: str, params: tuple = ()) -> sqlite3.Cursor:
    return await asyncio.get_event_loop().run_in_executor(None, _execute, query, params)


async def one(query: str, params: tuple = ()) -> Optional[sqlite3.Row]:
    return await asyncio.get_event_loop().run_in_executor(None, _fetchone, query, params)


async def all_(query: str, params: tuple = ()) -> List[sqlite3.Row]:
    return await asyncio.get_event_loop().run_in_executor(None, _fetchall, query, params)


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    vk_id INTEGER PRIMARY KEY,
    role TEXT NOT NULL DEFAULT 'user',
    nickname TEXT,
    first_seen TEXT NOT NULL,
    last_online TEXT
);

CREATE TABLE IF NOT EXISTS chat_stats (
    vk_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    msg_today INTEGER NOT NULL DEFAULT 0,
    msg_week INTEGER NOT NULL DEFAULT 0,
    msg_all INTEGER NOT NULL DEFAULT 0,
    last_day TEXT,
    last_week TEXT,
    PRIMARY KEY (vk_id, chat_id)
);

CREATE TABLE IF NOT EXISTS mutes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vk_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    until TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS punishments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vk_id INTEGER NOT NULL,
    kind TEXT NOT NULL,        -- 'mute' | 'ban'
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bans_chat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vk_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    chat_title TEXT,
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bans_pull (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vk_id INTEGER NOT NULL,
    pull_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS bans_global (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vk_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pulls (
    id INTEGER PRIMARY KEY,           -- номер сетки, задаваемый вручную через /setpull N
    name TEXT,
    parent_id INTEGER                 -- родительская сетка (направление/холдинг), см. /setdirection, /setholding
);

CREATE TABLE IF NOT EXISTS pull_roles (
    vk_id INTEGER NOT NULL,
    pull_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    PRIMARY KEY (vk_id, pull_id)
);

CREATE TABLE IF NOT EXISTS pull_chats (
    pull_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    PRIMARY KEY (pull_id, chat_id)
);

CREATE TABLE IF NOT EXISTS global_chats (
    chat_id INTEGER PRIMARY KEY,
    group_name TEXT
);

CREATE TABLE IF NOT EXISTS known_chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    first_seen TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_settings (
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    quiet_mode INTEGER NOT NULL DEFAULT 0,
    info_text TEXT
);

CREATE TABLE IF NOT EXISTS warns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vk_id INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    removed_by INTEGER,
    removed_at TEXT
);

-- Логирование сообщений: /logs назначает ЕДИНУЮ беседу-приёмник логов,
-- /go включает/выключает логирование конкретной беседы в неё.
CREATE TABLE IF NOT EXISTS log_config (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    log_chat_id INTEGER
);

CREATE TABLE IF NOT EXISTS log_enabled_chats (
    chat_id INTEGER PRIMARY KEY
);

-- Сквозная нумерация сообщений (#N) - отдельная последовательность для
-- каждой логируемой беседы. При редактировании номер не меняется - строка
-- для той же (chat_id, conversation_message_id) уже существует.
CREATE TABLE IF NOT EXISTS log_message_index (
    chat_id INTEGER NOT NULL,
    conversation_message_id INTEGER NOT NULL,
    log_number INTEGER NOT NULL,
    PRIMARY KEY (chat_id, conversation_message_id)
);

-- Автобан за самостоятельный выход из беседы ("чтобы не смог вернуться").
-- Три независимых уровня действия - беседа / сетка / глобально.
CREATE TABLE IF NOT EXISTS pull_leaveban (
    pull_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS global_leaveban (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled INTEGER NOT NULL DEFAULT 0
);

-- "Инфо-беседы" по организациям (см. handlers/info_chat_cmds.py, /addXinfo,
-- /delinfo) - куда рассылать объявления с сайта/Telegram-бота о назначениях
-- и наказаниях (см. bot_app/announce_server.py).
CREATE TABLE IF NOT EXISTS info_chats (
    org TEXT PRIMARY KEY,
    chat_id INTEGER NOT NULL,
    chat_title TEXT
);
"""


async def init_db() -> None:
    """Создаёт таблицы и назначает роль 'creator' пользователям из CREATOR_IDS."""
    await asyncio.get_event_loop().run_in_executor(None, _init_sync)
    for vk_id in config.CREATOR_IDS:
        await ensure_user(vk_id)
        await set_role(vk_id, "creator")


def _init_sync() -> None:
    with _lock:
        conn = _get_conn()
        conn.executescript(SCHEMA)
        _ensure_column(conn, "chat_settings", "leaveban", "INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, coldef: str) -> None:
    """Безопасно добавляет колонку в уже существующую таблицу, если её ещё нет
    (CREATE TABLE IF NOT EXISTS не меняет схему уже созданной таблицы)."""
    existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coldef}")


def _now() -> str:
    return datetime.datetime.utcnow().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Пользователи и роли
# ---------------------------------------------------------------------------

async def ensure_user(vk_id: int) -> None:
    row = await one("SELECT vk_id FROM users WHERE vk_id = ?", (vk_id,))
    if row is None:
        await run(
            "INSERT INTO users (vk_id, role, first_seen, last_online) VALUES (?, 'user', ?, ?)",
            (vk_id, _now(), _now()),
        )


async def get_role(vk_id: int) -> str:
    row = await one("SELECT role FROM users WHERE vk_id = ?", (vk_id,))
    return row["role"] if row else "user"


async def set_role(vk_id: int, role: str) -> None:
    await ensure_user(vk_id)
    await run("UPDATE users SET role = ? WHERE vk_id = ?", (role, vk_id))


async def touch_online(vk_id: int) -> None:
    await ensure_user(vk_id)
    await run("UPDATE users SET last_online = ? WHERE vk_id = ?", (_now(), vk_id))


async def get_user_row(vk_id: int):
    await ensure_user(vk_id)
    return await one("SELECT * FROM users WHERE vk_id = ?", (vk_id,))


async def get_nickname(vk_id: int) -> Optional[str]:
    row = await one("SELECT nickname FROM users WHERE vk_id = ?", (vk_id,))
    return row["nickname"] if row and row["nickname"] else None


async def set_nickname(vk_id: int, nickname: Optional[str]) -> None:
    await ensure_user(vk_id)
    await run("UPDATE users SET nickname = ? WHERE vk_id = ?", (nickname, vk_id))


async def find_by_nickname(nickname: str):
    return await one(
        "SELECT * FROM users WHERE lower(nickname) = lower(?)", (nickname,)
    )


async def list_staff() -> List[sqlite3.Row]:
    """Все пользователи с ролью лидер и выше, отсортированные по старшинству."""
    rows = await all_("SELECT * FROM users WHERE role != 'user'")
    from .hierarchy import role_level
    return sorted(rows, key=lambda r: role_level(r["role"]), reverse=True)


async def list_with_nicknames() -> List[sqlite3.Row]:
    return await all_(
        "SELECT * FROM users WHERE nickname IS NOT NULL AND nickname != ''"
    )


async def list_without_nicknames() -> List[sqlite3.Row]:
    return await all_(
        "SELECT * FROM users WHERE nickname IS NULL OR nickname = ''"
    )


# ---------------------------------------------------------------------------
# Статистика сообщений
# ---------------------------------------------------------------------------

async def bump_message_stat(vk_id: int, chat_id: int) -> None:
    today = datetime.date.today().isoformat()
    week = datetime.date.today().isocalendar()[1]
    row = await one(
        "SELECT * FROM chat_stats WHERE vk_id = ? AND chat_id = ?", (vk_id, chat_id)
    )
    if row is None:
        await run(
            """INSERT INTO chat_stats (vk_id, chat_id, msg_today, msg_week, msg_all, last_day, last_week)
               VALUES (?, ?, 1, 1, 1, ?, ?)""",
            (vk_id, chat_id, today, str(week)),
        )
        return

    msg_today = row["msg_today"] + 1 if row["last_day"] == today else 1
    msg_week = row["msg_week"] + 1 if row["last_week"] == str(week) else 1
    msg_all = row["msg_all"] + 1

    await run(
        """UPDATE chat_stats
           SET msg_today = ?, msg_week = ?, msg_all = ?, last_day = ?, last_week = ?
           WHERE vk_id = ? AND chat_id = ?""",
        (msg_today, msg_week, msg_all, today, str(week), vk_id, chat_id),
    )


async def get_total_messages(vk_id: int) -> Tuple[int, int, int]:
    rows = await all_("SELECT * FROM chat_stats WHERE vk_id = ?", (vk_id,))
    today = datetime.date.today().isoformat()
    week = str(datetime.date.today().isocalendar()[1])
    msg_today = sum(r["msg_today"] for r in rows if r["last_day"] == today)
    msg_week = sum(r["msg_week"] for r in rows if r["last_week"] == week)
    msg_all = sum(r["msg_all"] for r in rows)
    return msg_today, msg_week, msg_all


# ---------------------------------------------------------------------------
# Муты
# ---------------------------------------------------------------------------

async def add_mute(vk_id: int, chat_id: int, moderator_id: int, reason: str, until: datetime.datetime) -> None:
    await run(
        """INSERT INTO mutes (vk_id, chat_id, moderator_id, reason, until, active)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (vk_id, chat_id, moderator_id, reason, until.isoformat(timespec="seconds")),
    )
    await run(
        "INSERT INTO punishments (vk_id, kind, moderator_id, reason, created_at) VALUES (?, 'mute', ?, ?, ?)",
        (vk_id, moderator_id, reason, _now()),
    )


async def remove_mute(vk_id: int, chat_id: int) -> None:
    await run(
        "UPDATE mutes SET active = 0 WHERE vk_id = ? AND chat_id = ? AND active = 1",
        (vk_id, chat_id),
    )


async def is_muted(vk_id: int, chat_id: int) -> bool:
    row = await one(
        """SELECT * FROM mutes WHERE vk_id = ? AND chat_id = ? AND active = 1
           ORDER BY id DESC LIMIT 1""",
        (vk_id, chat_id),
    )
    if row is None:
        return False
    until = datetime.datetime.fromisoformat(row["until"])
    if until <= datetime.datetime.utcnow():
        await remove_mute(vk_id, chat_id)
        return False
    return True


async def count_mutes(vk_id: int) -> int:
    row = await one("SELECT COUNT(*) as c FROM punishments WHERE vk_id = ? AND kind = 'mute'", (vk_id,))
    return row["c"] if row else 0


async def count_bans(vk_id: int) -> int:
    row = await one("SELECT COUNT(*) as c FROM punishments WHERE vk_id = ? AND kind = 'ban'", (vk_id,))
    return row["c"] if row else 0


# ---------------------------------------------------------------------------
# Баны (чат / сетка / глобально)
# ---------------------------------------------------------------------------

async def add_chat_ban(vk_id: int, chat_id: int, chat_title: str, moderator_id: int, reason: str) -> None:
    await run(
        """INSERT INTO bans_chat (vk_id, chat_id, chat_title, moderator_id, reason, created_at, active)
           VALUES (?, ?, ?, ?, ?, ?, 1)""",
        (vk_id, chat_id, chat_title, moderator_id, reason, _now()),
    )
    await run(
        "INSERT INTO punishments (vk_id, kind, moderator_id, reason, created_at) VALUES (?, 'ban', ?, ?, ?)",
        (vk_id, moderator_id, reason, _now()),
    )


async def remove_chat_ban(vk_id: int, chat_id: int) -> bool:
    cur = await run(
        "UPDATE bans_chat SET active = 0 WHERE vk_id = ? AND chat_id = ? AND active = 1",
        (vk_id, chat_id),
    )
    return cur.rowcount > 0


async def is_chat_banned(vk_id: int, chat_id: int) -> bool:
    row = await one(
        "SELECT id FROM bans_chat WHERE vk_id = ? AND chat_id = ? AND active = 1", (vk_id, chat_id)
    )
    return row is not None


async def list_chat_bans_for_user(vk_id: int) -> List[sqlite3.Row]:
    return await all_(
        "SELECT * FROM bans_chat WHERE vk_id = ? AND active = 1 ORDER BY created_at DESC", (vk_id,)
    )


async def list_banned_in_chat(chat_id: int) -> List[sqlite3.Row]:
    return await all_(
        "SELECT * FROM bans_chat WHERE chat_id = ? AND active = 1", (chat_id,)
    )


async def add_pull_ban(vk_id: int, pull_id: int, moderator_id: int, reason: str) -> None:
    await run(
        """INSERT INTO bans_pull (vk_id, pull_id, moderator_id, reason, created_at, active)
           VALUES (?, ?, ?, ?, ?, 1)""",
        (vk_id, pull_id, moderator_id, reason, _now()),
    )
    await run(
        "INSERT INTO punishments (vk_id, kind, moderator_id, reason, created_at) VALUES (?, 'ban', ?, ?, ?)",
        (vk_id, moderator_id, reason, _now()),
    )


async def remove_pull_ban(vk_id: int, pull_id: int) -> bool:
    cur = await run(
        "UPDATE bans_pull SET active = 0 WHERE vk_id = ? AND pull_id = ? AND active = 1",
        (vk_id, pull_id),
    )
    return cur.rowcount > 0


async def is_pull_banned(vk_id: int, pull_id: int) -> bool:
    row = await one(
        "SELECT id FROM bans_pull WHERE vk_id = ? AND pull_id = ? AND active = 1", (vk_id, pull_id)
    )
    return row is not None


async def list_pull_bans_for_user(vk_id: int) -> List[sqlite3.Row]:
    return await all_(
        "SELECT * FROM bans_pull WHERE vk_id = ? AND active = 1 ORDER BY created_at DESC", (vk_id,)
    )


async def add_global_ban(vk_id: int, moderator_id: int, reason: str) -> None:
    await run(
        """INSERT INTO bans_global (vk_id, moderator_id, reason, created_at, active)
           VALUES (?, ?, ?, ?, 1)""",
        (vk_id, moderator_id, reason, _now()),
    )
    await run(
        "INSERT INTO punishments (vk_id, kind, moderator_id, reason, created_at) VALUES (?, 'ban', ?, ?, ?)",
        (vk_id, moderator_id, reason, _now()),
    )


async def remove_global_ban(vk_id: int) -> bool:
    cur = await run("UPDATE bans_global SET active = 0 WHERE vk_id = ? AND active = 1", (vk_id,))
    return cur.rowcount > 0


async def is_globally_banned(vk_id: int) -> bool:
    row = await one("SELECT id FROM bans_global WHERE vk_id = ? AND active = 1", (vk_id,))
    return row is not None


async def get_global_ban(vk_id: int):
    return await one(
        "SELECT * FROM bans_global WHERE vk_id = ? AND active = 1 ORDER BY created_at DESC LIMIT 1",
        (vk_id,),
    )


# ---------------------------------------------------------------------------
# Сетки бесед (pulls) и глобальные беседы
# ---------------------------------------------------------------------------

async def create_or_get_pull(pull_id: int) -> None:
    row = await one("SELECT id FROM pulls WHERE id = ?", (pull_id,))
    if row is None:
        await run("INSERT INTO pulls (id, name) VALUES (?, ?)", (pull_id, str(pull_id)))


async def attach_chat_to_pull(chat_id: int, pull_id: int) -> None:
    await create_or_get_pull(pull_id)
    await run(
        "INSERT OR IGNORE INTO pull_chats (pull_id, chat_id) VALUES (?, ?)",
        (pull_id, chat_id),
    )


async def detach_chat_from_pull(chat_id: int, pull_id: int) -> bool:
    cur = await run(
        "DELETE FROM pull_chats WHERE pull_id = ? AND chat_id = ?", (pull_id, chat_id)
    )
    return cur.rowcount > 0


async def get_pull_of_chat(chat_id: int) -> Optional[int]:
    row = await one("SELECT pull_id FROM pull_chats WHERE chat_id = ?", (chat_id,))
    return row["pull_id"] if row else None


async def get_chats_in_pull(pull_id: int) -> List[int]:
    rows = await all_("SELECT chat_id FROM pull_chats WHERE pull_id = ?", (pull_id,))
    return [r["chat_id"] for r in rows]


# ---------------------------------------------------------------------------
# Иерархия сеток: организация -> направление -> все организации (холдинг).
# У сетки может быть родительская сетка (parent_id). См. /setdirection,
# /setholding в creator_cmds.py.
# ---------------------------------------------------------------------------

async def set_pull_parent(pull_id: int, parent_pull_id: int) -> None:
    await create_or_get_pull(pull_id)
    await create_or_get_pull(parent_pull_id)
    await run("UPDATE pulls SET parent_id = ? WHERE id = ?", (parent_pull_id, pull_id))


async def remove_pull_parent(pull_id: int) -> None:
    await run("UPDATE pulls SET parent_id = NULL WHERE id = ?", (pull_id,))


async def get_pull_parent(pull_id: int) -> Optional[int]:
    row = await one("SELECT parent_id FROM pulls WHERE id = ?", (pull_id,))
    return row["parent_id"] if row and row["parent_id"] is not None else None


async def get_pull_chain(pull_id: int, max_depth: int = 10) -> List[int]:
    """
    [сама_сетка, родитель, дед, ...] - поднимается вверх по иерархии.
    Ограничение глубины - защита от случайно созданного цикла.
    """
    chain = [pull_id]
    current = pull_id
    for _ in range(max_depth):
        parent = await get_pull_parent(current)
        if parent is None or parent in chain:
            break
        chain.append(parent)
        current = parent
    return chain


async def get_chats_in_pull_chain(pull_id: int) -> List[int]:
    """
    Собственные беседы сетки + собственные беседы каждой сетки-предка
    (направления, холдинга), без дублей. Именно этот список используется
    для каскадных /skick, /sban, /sunban, /szov - если сетка "Л-ОПГ" вложена
    в сетку направления "Криминальные", а та - в сетку "Все организации", то
    команда, вызванная из беседы Л-ОПГ, затронет и её, и беседу направления,
    и общую беседу всех организаций.
    """
    chain = await get_pull_chain(pull_id)
    seen = set()
    result = []
    for pid in chain:
        for chat_id in await get_chats_in_pull(pid):
            if chat_id not in seen:
                seen.add(chat_id)
                result.append(chat_id)
    return result


async def add_global_chat(chat_id: int, group_name: str) -> None:
    await run(
        "INSERT OR REPLACE INTO global_chats (chat_id, group_name) VALUES (?, ?)",
        (chat_id, group_name),
    )


async def remove_global_chat(chat_id: int) -> bool:
    cur = await run("DELETE FROM global_chats WHERE chat_id = ?", (chat_id,))
    return cur.rowcount > 0


async def list_global_chats() -> List[sqlite3.Row]:
    return await all_("SELECT * FROM global_chats")


async def get_global_group_name(chat_id: int) -> Optional[str]:
    row = await one("SELECT group_name FROM global_chats WHERE chat_id = ?", (chat_id,))
    return row["group_name"] if row else None


# ---------------------------------------------------------------------------
# Все беседы, куда добавлен бот (авто-регистрация, без ручных команд)
# ---------------------------------------------------------------------------

async def ensure_known_chat(chat_id: int, title: Optional[str] = None) -> None:
    row = await one("SELECT chat_id FROM known_chats WHERE chat_id = ?", (chat_id,))
    if row is None:
        await run(
            "INSERT INTO known_chats (chat_id, title, first_seen) VALUES (?, ?, ?)",
            (chat_id, title, _now()),
        )
    elif title:
        await run("UPDATE known_chats SET title = ? WHERE chat_id = ?", (title, chat_id))


async def forget_known_chat(chat_id: int) -> bool:
    """Вызывается, когда бота удаляют из беседы (kick_user_of_group)."""
    cur = await run("DELETE FROM known_chats WHERE chat_id = ?", (chat_id,))
    return cur.rowcount > 0


async def list_known_chat_ids() -> List[int]:
    rows = await all_("SELECT chat_id FROM known_chats")
    return [r["chat_id"] for r in rows]


# ---------------------------------------------------------------------------
# Настройки беседы (тишина, лог-чат, название, инфо-текст)
# ---------------------------------------------------------------------------

async def ensure_chat_settings(chat_id: int) -> None:
    row = await one("SELECT chat_id FROM chat_settings WHERE chat_id = ?", (chat_id,))
    if row is None:
        await run("INSERT INTO chat_settings (chat_id) VALUES (?)", (chat_id,))


async def get_chat_settings(chat_id: int):
    await ensure_chat_settings(chat_id)
    return await one("SELECT * FROM chat_settings WHERE chat_id = ?", (chat_id,))


async def set_quiet_mode(chat_id: int, enabled: bool) -> None:
    await ensure_chat_settings(chat_id)
    await run("UPDATE chat_settings SET quiet_mode = ? WHERE chat_id = ?", (1 if enabled else 0, chat_id))


async def is_quiet_mode(chat_id: int) -> bool:
    row = await get_chat_settings(chat_id)
    return bool(row["quiet_mode"]) if row else False


# ---------------------------------------------------------------------------
# Автобан за самостоятельный выход из беседы (/leaveban, /sleaveban, /gleaveban)
# ---------------------------------------------------------------------------

async def toggle_chat_leaveban(chat_id: int) -> bool:
    """Переключает и возвращает НОВОЕ состояние (как /quiet)."""
    current = await is_chat_leaveban(chat_id)
    new_state = not current
    await ensure_chat_settings(chat_id)
    await run("UPDATE chat_settings SET leaveban = ? WHERE chat_id = ?", (1 if new_state else 0, chat_id))
    return new_state


async def is_chat_leaveban(chat_id: int) -> bool:
    row = await get_chat_settings(chat_id)
    return bool(row["leaveban"]) if row else False


async def toggle_pull_leaveban(pull_id: int) -> bool:
    if await is_pull_leaveban(pull_id):
        await run("DELETE FROM pull_leaveban WHERE pull_id = ?", (pull_id,))
        return False
    await run("INSERT OR IGNORE INTO pull_leaveban (pull_id) VALUES (?)", (pull_id,))
    return True


async def is_pull_leaveban(pull_id: int) -> bool:
    row = await one("SELECT pull_id FROM pull_leaveban WHERE pull_id = ?", (pull_id,))
    return row is not None


async def toggle_global_leaveban() -> bool:
    new_state = not await is_global_leaveban()
    await run(
        "INSERT INTO global_leaveban (id, enabled) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET enabled = excluded.enabled",
        (1 if new_state else 0,),
    )
    return new_state


async def is_global_leaveban() -> bool:
    row = await one("SELECT enabled FROM global_leaveban WHERE id = 1")
    return bool(row["enabled"]) if row else False


async def set_chat_title(chat_id: int, title: str) -> None:
    await ensure_chat_settings(chat_id)
    await run("UPDATE chat_settings SET title = ? WHERE chat_id = ?", (title, chat_id))


async def set_info_text(text: str) -> None:
    """Глобальный текст для команды /info (единый на весь проект)."""
    await run(
        "INSERT INTO chat_settings (chat_id, info_text) VALUES (0, ?) "
        "ON CONFLICT(chat_id) DO UPDATE SET info_text = excluded.info_text",
        (text,),
    )


async def get_info_text() -> Optional[str]:
    row = await one("SELECT info_text FROM chat_settings WHERE chat_id = 0")
    return row["info_text"] if row and row["info_text"] else None


# ---------------------------------------------------------------------------
# Логирование сообщений (/logs, /go)
# ---------------------------------------------------------------------------

async def set_global_log_chat(chat_id: int) -> None:
    """/logs - назначает ЭТУ беседу единым приёмником логов."""
    await run(
        "INSERT INTO log_config (id, log_chat_id) VALUES (1, ?) "
        "ON CONFLICT(id) DO UPDATE SET log_chat_id = excluded.log_chat_id",
        (chat_id,),
    )


async def get_global_log_chat() -> Optional[int]:
    row = await one("SELECT log_chat_id FROM log_config WHERE id = 1")
    return row["log_chat_id"] if row and row["log_chat_id"] is not None else None


async def enable_logging(chat_id: int) -> None:
    await run("INSERT OR IGNORE INTO log_enabled_chats (chat_id) VALUES (?)", (chat_id,))


async def disable_logging(chat_id: int) -> bool:
    cur = await run("DELETE FROM log_enabled_chats WHERE chat_id = ?", (chat_id,))
    return cur.rowcount > 0


async def is_logging_enabled(chat_id: int) -> bool:
    row = await one("SELECT chat_id FROM log_enabled_chats WHERE chat_id = ?", (chat_id,))
    return row is not None


async def get_or_assign_log_number(chat_id: int, conversation_message_id: int) -> int:
    """
    Возвращает номер #N для этого сообщения в рамках ЭТОЙ беседы: если оно
    уже логировалось раньше (например, это повторный вызов при
    редактировании) - отдаёт тот же номер, иначе выдаёт следующий по счёту.
    """
    row = await one(
        "SELECT log_number FROM log_message_index WHERE chat_id = ? AND conversation_message_id = ?",
        (chat_id, conversation_message_id),
    )
    if row:
        return row["log_number"]

    row = await one(
        "SELECT COALESCE(MAX(log_number), 0) as m FROM log_message_index WHERE chat_id = ?",
        (chat_id,),
    )
    next_number = (row["m"] if row else 0) + 1
    await run(
        "INSERT OR IGNORE INTO log_message_index (chat_id, conversation_message_id, log_number) VALUES (?, ?, ?)",
        (chat_id, conversation_message_id, next_number),
    )
    return next_number


async def get_log_number(chat_id: int, conversation_message_id: int) -> Optional[int]:
    """Только посмотреть номер (не назначает новый) - для строки "Ответил на сообщение: #N"."""
    row = await one(
        "SELECT log_number FROM log_message_index WHERE chat_id = ? AND conversation_message_id = ?",
        (chat_id, conversation_message_id),
    )
    return row["log_number"] if row else None


# ---------------------------------------------------------------------------
# Предупреждения (варны)
# ---------------------------------------------------------------------------

async def add_warn(vk_id: int, moderator_id: int, reason: str) -> int:
    """Добавляет активное предупреждение. Возвращает новое количество активных варнов."""
    await run(
        """INSERT INTO warns (vk_id, moderator_id, reason, created_at, active)
           VALUES (?, ?, ?, ?, 1)""",
        (vk_id, moderator_id, reason, _now()),
    )
    return await count_active_warns(vk_id)


async def remove_latest_warn(vk_id: int, moderator_id: int):
    """Снимает самое свежее активное предупреждение. Возвращает снятую запись или None."""
    row = await one(
        "SELECT * FROM warns WHERE vk_id = ? AND active = 1 ORDER BY id DESC LIMIT 1",
        (vk_id,),
    )
    if row is None:
        return None
    await run(
        "UPDATE warns SET active = 0, removed_by = ?, removed_at = ? WHERE id = ?",
        (moderator_id, _now(), row["id"]),
    )
    return row


async def count_active_warns(vk_id: int) -> int:
    row = await one("SELECT COUNT(*) as c FROM warns WHERE vk_id = ? AND active = 1", (vk_id,))
    return row["c"] if row else 0


async def list_active_warns(vk_id: int) -> List[sqlite3.Row]:
    return await all_(
        "SELECT * FROM warns WHERE vk_id = ? AND active = 1 ORDER BY created_at ASC", (vk_id,)
    )


async def list_warn_history(vk_id: int) -> List[sqlite3.Row]:
    return await all_(
        "SELECT * FROM warns WHERE vk_id = ? ORDER BY created_at ASC", (vk_id,)
    )


async def list_users_with_active_warns() -> List[sqlite3.Row]:
    """Пользователи с хотя бы одним активным варном + счётчик."""
    return await all_(
        """SELECT vk_id, COUNT(*) as cnt FROM warns
           WHERE active = 1 GROUP BY vk_id ORDER BY cnt DESC"""
    )


# ---------------------------------------------------------------------------
# Роли внутри сетки бесед (pull_roles) и "эффективная" роль
# ---------------------------------------------------------------------------

async def set_pull_role(vk_id: int, pull_id: int, role: str) -> None:
    await run(
        """INSERT INTO pull_roles (vk_id, pull_id, role) VALUES (?, ?, ?)
           ON CONFLICT(vk_id, pull_id) DO UPDATE SET role = excluded.role""",
        (vk_id, pull_id, role),
    )


async def remove_pull_role(vk_id: int, pull_id: int) -> bool:
    cur = await run(
        "DELETE FROM pull_roles WHERE vk_id = ? AND pull_id = ?", (vk_id, pull_id)
    )
    return cur.rowcount > 0


async def get_pull_role(vk_id: int, pull_id: int) -> Optional[str]:
    row = await one(
        "SELECT role FROM pull_roles WHERE vk_id = ? AND pull_id = ?", (vk_id, pull_id)
    )
    return row["role"] if row else None


async def get_effective_role(vk_id: int, chat_id: Optional[int]) -> str:
    """
    Роль пользователя ДЛЯ КОНКРЕТНОЙ БЕСЕДЫ: если у беседы есть сетка и в
    этой сетке пользователю выдана отдельная роль (через /saddld, /srole и
    т.п.) - учитывается более старшая из двух: глобальной и "сеточной".
    Для личных сообщений (chat_id is None) используется просто глобальная роль.
    """
    global_role = await get_role(vk_id)
    if chat_id is None:
        return global_role

    pull_id = await get_pull_of_chat(chat_id)
    if pull_id is None:
        return global_role

    pull_role = await get_pull_role(vk_id, pull_id)
    if pull_role is None:
        return global_role

    return global_role if role_level(global_role) >= role_level(pull_role) else pull_role


# ---------------------------------------------------------------------------
# Инфо-беседы по организациям (мост с сайтом, см. handlers/info_chat_cmds.py
# и bot_app/announce_server.py)
# ---------------------------------------------------------------------------

async def set_info_chat(org: str, chat_id: int, chat_title: str = None) -> None:
    await run(
        "INSERT INTO info_chats (org, chat_id, chat_title) VALUES (?, ?, ?) "
        "ON CONFLICT(org) DO UPDATE SET chat_id = excluded.chat_id, chat_title = excluded.chat_title",
        (org, chat_id, chat_title),
    )


async def get_info_chat(org: str) -> Optional[int]:
    row = await one("SELECT chat_id FROM info_chats WHERE org = ?", (org,))
    return row["chat_id"] if row else None


async def remove_info_chat_by_chat_id(chat_id: int) -> Optional[str]:
    """Используется /delinfo - снимает привязку ТЕКУЩЕЙ беседы, какой бы
    организации она ни принадлежала. Возвращает название организации,
    которая была отвязана, или None, если эта беседа не была инфо-беседой."""
    row = await one("SELECT org FROM info_chats WHERE chat_id = ?", (chat_id,))
    if row is None:
        return None
    await run("DELETE FROM info_chats WHERE chat_id = ?", (chat_id,))
    return row["org"]


async def list_info_chats() -> List[sqlite3.Row]:
    return await all_("SELECT * FROM info_chats")
