"""
Три вида служебных событий беседы:
1) Бота добавили/удалили из беседы -> ведём список known_chats
   (используется командами /gban, /gunban, /gkick, /gzov - они действуют
   на ВСЕ беседы из этого списка, без необходимости отдельно прописывать
   /global).
2) В беседу добавили пользователя -> проверяем баны (глобальный / по
   сетке / по этой беседе) и кикаем при необходимости, либо приветствуем.
3) Пользователь вышел из беседы САМ (chat_kick_user, где member_id == тот,
   кто прислал это служебное сообщение) -> если для этой беседы/сетки/
   глобально включён /leaveban - баним его, чтобы не смог вернуться по
   кнопке "Вернуться" или через повторное приглашение (см. _check_and_kick_banned).
"""
from .. import database, utils, chat_utils, config
from ..bot_instance import bot
from ..rules import ActionRule
from ..hierarchy import has_min_role


@bot.on.message(ActionRule("chat_invite_user"))
async def on_chat_invite(message):
    action = message.action
    target_id = getattr(action, "member_id", None)
    peer_id = message.peer_id
    chat_id = chat_utils.chat_id_from_peer(peer_id)

    if target_id is not None and target_id == -config.VK_GROUP_ID:
        # Пригласили самого бота - регистрируем беседу.
        title = await chat_utils.get_conversation_title(message.ctx_api, peer_id)
        await database.ensure_known_chat(chat_id, title)
        return

    # Приглашать людей в беседу могут только Лидер и выше - если пригласил
    # Старший состав (или вообще человек без роли), приглашённого сразу кикаем,
    # до проверки банов и приветствия.
    if target_id and target_id > 0 and message.from_id != target_id:
        inviter_role = await database.get_effective_role(message.from_id, chat_id)
        if not has_min_role(inviter_role, "leader"):
            await chat_utils.kick_member(message.ctx_api, peer_id, target_id)
            target_link = await utils.profile_link_auto(message.ctx_api, target_id)
            await message.answer(
                f"{target_link} был(-а) кикнут - приглашать в беседу могут только Лидер и выше."
            )
            return

    await _check_and_kick_banned(message, target_id, peer_id, chat_id)


@bot.on.message(ActionRule("chat_kick_user"))
async def on_chat_kick(message):
    action = message.action
    target_id = getattr(action, "member_id", None)
    peer_id = message.peer_id
    chat_id = chat_utils.chat_id_from_peer(peer_id)

    if target_id is not None and target_id == -config.VK_GROUP_ID:
        # Бота удалили из беседы - забываем её (не будет учитываться в /g...).
        await database.forget_known_chat(chat_id)
        return

    # Самостоятельный выход: VK присылает это же служебное сообщение и когда
    # человека кикнули (from_id - модератор), и когда он вышел сам
    # (from_id == member_id, то есть указывает сам на себя).
    if target_id and target_id > 0 and message.from_id == target_id:
        await _handle_self_leave(message, target_id, chat_id, peer_id)


async def _handle_self_leave(message, target_id: int, chat_id: int, peer_id: int) -> None:
    reason = "Самостоятельный выход из беседы"
    SYSTEM_MODERATOR_ID = 0  # автоматическое действие бота, не конкретный человек

    if await database.is_global_leaveban():
        await database.add_global_ban(target_id, SYSTEM_MODERATOR_ID, reason)
        return

    pull_id = await database.get_pull_of_chat(chat_id)
    if pull_id is not None:
        chain = await database.get_pull_chain(pull_id)
        chain_flags = [await database.is_pull_leaveban(pid) for pid in chain]
        if any(chain_flags):
            for pid in chain:
                await database.add_pull_ban(target_id, pid, SYSTEM_MODERATOR_ID, reason)
            return

    if await database.is_chat_leaveban(chat_id):
        title = await chat_utils.get_conversation_title(message.ctx_api, peer_id)
        await database.add_chat_ban(target_id, chat_id, title, SYSTEM_MODERATOR_ID, reason)


async def _check_and_kick_banned(message, target_id, peer_id, chat_id):
    if not target_id or target_id < 0:
        return  # приглашение сообщества, а не пользователя

    LEAVE_REASON = "Самостоятельный выход из беседы"
    reason_line = None
    is_leave_kick = False

    if await database.is_globally_banned(target_id):
        ban = await database.get_global_ban(target_id)
        is_leave_kick = ban["reason"] == LEAVE_REASON
        mod_link = utils.role_label_link(ban["moderator_id"], "Модератор")
        reason_line = (
            f"заблокирован во всех беседах | {mod_link} | {ban['reason'] or '-'} | {utils.format_msk(ban['created_at'])}"
        )
    else:
        pull_id = await database.get_pull_of_chat(chat_id)
        if pull_id is not None and await database.is_pull_banned(target_id, pull_id):
            bans = await database.list_pull_bans_for_user(target_id)
            ban = bans[0]
            is_leave_kick = ban["reason"] == LEAVE_REASON
            mod_link = utils.role_label_link(ban["moderator_id"], "Модератор")
            reason_line = (
                f"заблокирован в сетке беседы | {mod_link} | {ban['reason'] or '-'} | {utils.format_msk(ban['created_at'])}"
            )
        elif await database.is_chat_banned(target_id, chat_id):
            bans = await database.list_chat_bans_for_user(target_id)
            ban = bans[0]
            is_leave_kick = ban["reason"] == LEAVE_REASON
            mod_link = utils.role_label_link(ban["moderator_id"], "Модератор")
            reason_line = (
                f"заблокирован в этой беседе | {mod_link} | {ban['reason'] or '-'} | {utils.format_msk(ban['created_at'])}"
            )

    if reason_line is not None:
        await chat_utils.kick_member(message.ctx_api, peer_id, target_id)
        target_link = await utils.profile_link_auto(message.ctx_api, target_id)
        if is_leave_kick:
            # /leaveban - это не полноценный бан модератором с причиной, а просто
            # "не пускать обратно того, кто сам вышел" - короткое сообщение без
            # слова "забанен"/имени модератора (модератор здесь - сам бот).
            await message.answer(f"{target_link} был(-а) кикнут.")
        else:
            await message.answer(f"{target_link} {reason_line}.")
        return

    # Не забанен - приветствуем в беседе.
    first_name = await utils.get_user_first_name(message.ctx_api, target_id)
    mention = f"[id{target_id}|{first_name}]"
    await message.answer(
        f"{mention}, добро пожаловать в беседу!\n"
        "Не забудь прочитать закреплённое сообщение!\n"
        "Посмотреть информацию о проекте: «/info»"
    )
