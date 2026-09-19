"""
Импорт всех модулей с хендлерами. Порядок важен: guard-модули (статистика,
муты, защита от входа забаненных) регистрируются первыми.
"""
from . import mute_guard          # noqa: F401  (статистика + автоудаление у замученных)
from . import message_logger      # noqa: F401  (логирование сообщений, /go, /logs)
from . import join_guard          # noqa: F401  (автокик забаненных при входе, приветствие)
from . import user_cmds           # noqa: F401  (getid, stats, info, help, alt)
from . import leader_cmds         # noqa: F401  (kick, mute, unmute, staff, nlist, ...)
from . import nick_list_cmds      # noqa: F401  (nlist, nonick, getnick с пагинацией)
from . import role_cmds           # noqa: F401  (addld/addsup/.../role/srole/rrole/removerole)
from . import tracker_cmds        # noqa: F401  (ban, unban, banlist, quiet)
from . import senior_tracker_cmds  # noqa: F401  (sban, sunban, szov)
from . import leadership_cmds     # noqa: F401  (gban, gunban, gkick, gzov, setinfo)
from . import creator_cmds        # noqa: F401  (setpull, delpull, global, delglobal, nickname, go, logs)
from . import info_chat_cmds      # noqa: F401  (addXinfo/delinfo - скрытые команды создателя, мост с сайтом)
from . import callbacks           # noqa: F401  (обработка нажатий на инлайн-кнопки)
