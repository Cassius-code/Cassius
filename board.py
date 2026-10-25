"""📌 «Проёб»da qadalgan «Задержки сейчас»: har RD — hozir nechta lid limitdan oshib javobsiz turibdi
(🟢 yo'q · 🟡 bor · 🔴 ko'p — jarima chegarasi). Bosh menyudagi bilan bir xil son. Pul yo'q — hamma ko'radi.
Bitta xabar: guruh tepasida qadalgan, son o'zgarsa — o'sha xabar joyida yangilanadi (yangi xabar yozilmaydi)."""
from __future__ import annotations

import logging

from . import people as P
from .gtext import esc

log = logging.getLogger("board")

EVERY = 5                    # soniya: shunchada bir tekshiriladi, son o'zgargandagina tahrirlanadi


def text(ctx, now: int) -> str:
    db, tr = ctx.db, ctx.tracker
    lines = ["<b>🚨 Задержки сейчас</b>"]
    if not db.flag("delay_enabled"):
        return "\n".join(lines + ["⚪ контроль выключен"])
    over = tr.live_counts(now)["overdue"]
    red = max(1, tr.fine_rules()[0])
    for f in P.folders(db):
        if not f["delay_on"]:
            continue
        n = over.get(f["id"], 0)
        lines.append(f"{'🟢' if n == 0 else ('🔴' if n >= red else '🟡')} {esc(f['name'])} — <b>{n}</b>")
    return "\n".join(lines)


async def refresh(ctx, now: int, force: bool = False) -> None:
    """Doska yo'q bo'lsa — yoziladi va qadaladi; bor bo'lsa — son o'zgargandagina tahrirlanadi."""
    db, n = ctx.db, ctx.notifier
    if not db.flag("board_on") or not db.flag("bot_enabled"):
        return
    try:
        gid = n.group_id()
    except Exception:
        return
    body = text(ctx, now)
    mid = db.get_int("board_msg_id")
    if mid and db.get("board_gid") == str(gid):
        if body == db.get("board_text") and not force:
            return
        try:
            await n._call(n.bot.edit_message_text, chat_id=gid, message_id=mid, text=body, parse_mode="HTML",
                          disable_web_page_preview=True)
            db.set("board_text", body)
            return
        except Exception as exc:
            low = str(exc).lower()
            if "not modified" in low:
                db.set("board_text", body)
                return
            if not any(k in low for k in ("not found", "can't be edited", "message to edit")):
                log.info("Doska yangilanmadi: %s", exc)              # tarmoq va h.k. — keyingi safar
                return
    msg = await n._call(n.bot.send_message, chat_id=gid, text=body, parse_mode="HTML",
                        disable_notification=True, disable_web_page_preview=True)
    db.set("board_msg_id", str(msg.message_id))
    db.set("board_gid", str(msg.chat.id))
    db.set("board_text", body)
    try:
        await n.bot.pin_chat_message(chat_id=msg.chat.id, message_id=msg.message_id, disable_notification=True)
    except Exception as exc:
        log.info("Doska qadalmadi: %s", exc)
        from .context import tr
        await n.notify_owner(lambda: (tr(
            "📌 «Задержки сейчас» «Проёб»ga yozildi, lekin qadab bo'lmadi. Botga guruhda «Xabarlarni qadash» "
            "huquqini bering: guruh → ✏️ → Administratorlar → bot.",
            "📌 «Задержки сейчас» отправлено в «Проёб», но закрепить не удалось. Дайте боту право «Закреплять "
            "сообщения»: группа → ✏️ → Администраторы → бот."), None), key="board-pin", min_interval=86400)


async def remove(ctx) -> None:
    """O'chirildi: qadash olinadi va xabar o'chadi."""
    db, n = ctx.db, ctx.notifier
    mid, gid = db.get_int("board_msg_id"), db.get("board_gid")
    if mid and gid.lstrip("-").isdigit():
        try:
            await n.bot.unpin_chat_message(chat_id=int(gid), message_id=mid)
        except Exception:
            pass
        try:
            await n.bot.delete_message(chat_id=int(gid), message_id=mid)
        except Exception:
            pass
    db.set("board_msg_id", "")
    db.set("board_text", "")
