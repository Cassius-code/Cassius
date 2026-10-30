"""📌 «Проёб»da qadalgan «Задержки сейчас» — har RD rangli holat (egasi bilan kelishilgan, 2026-10-30):

    🟢 — 15+ daqiqa kutayotgan lid yo'q (kamroq kutayotganlar bo'lishi mumkin);
    🟡 — 15–19 daqiqa kutayotgan lid bor (limitdan 5 daqiqa oldin);
    🔴 — 20+ daqiqa (zaderjka).

Soat — zaderjkadagi bilan bir xil: faqat ish vaqti, tanaffus pauzasisiz, ⚡/💊 va stavkadagilarsiz. Doska o'z fon
vazifasida ishlaydi (boshqa xabarlarni kutib qolmaydi): har 3 soniyada hisoblanadi, o'zgargan bo'lsa ~10 soniyada
o'z joyida yangilanadi. Telegram «kuting» desa — kutib yana uradi. Xabar o'chirilsa — qaytadan yoziladi va qadaladi.
Pul yo'q — hamma ko'radi."""
from __future__ import annotations

import asyncio
import logging
import time

from . import people as P
from .gtext import esc, small

log = logging.getLogger("board")

EVERY = 3                    # soniya: shunchada bir hisoblanadi
MIN_EDIT = 10                # ikki tahrir orasida kamida (guruhga ko'p yozish cheklanadi)
_state = {"edit": 0.0, "pause": 0.0}


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def rows(ctx, now: int) -> list[tuple]:
    """[(papka, 🔴 soni, 🟡 soni)] — nazoratdagi papkalar."""
    lc = ctx.tracker.live_counts(now)
    over, near = lc["overdue"], lc.get("near", {})
    return [(f, over.get(f["id"], 0), near.get(f["id"], 0)) for f in P.folders(ctx.db) if f["delay_on"]]


def icon(red: int, near: int) -> str:
    return "🔴" if red else ("🟡" if near else "🟢")


def text(ctx, now: int) -> str:
    """Birinchi qator — guruh tepasidagi qadalgan satrda ko'rinadi (bosmasdan ham)."""
    db, tr = ctx.db, ctx.tracker
    if not db.flag("delay_enabled"):
        return "<b>🚨 Задержки сейчас</b>\n⚪ контроль выключен"
    warn = tr.warn_seconds() // 60
    data = rows(ctx, now)
    total = sum(r for _f, r, _n in data)
    soon = sum(n for _f, _r, n in data)
    if total:
        worst = sorted((x for x in data if x[1]), key=lambda x: -x[1])
        first = f"<b>🚨 Задержки сейчас: {total}</b> · " + " · ".join(f"{esc(f['name'])} — {r}" for f, r, _n in worst)
    elif soon:
        first = f"<b>🟡 Задержек нет</b> · ждут {warn}+ мин: {soon}"
    else:
        first = "<b>🟢 Задержек нет</b>"
    lines = [first, ""]
    for f, red, near in data:
        bits = []
        if red:
            bits.append(f"{red} {_plural(red, 'задержка', 'задержки', 'задержек')}")
        if near:
            bits.append(f"{near} {'ждёт' if near == 1 else 'ждут'} {warn}+ мин")
        lines.append(f"{icon(red, near)} {esc(f['name'])}" + (f" — {' · '.join(bits)}" if bits else ""))
    from .timeutil import fmt
    lines += ["", small(f"🟢 нет ждущих {warn}+ мин · 🟡 ждут {warn}+ мин · 🔴 задержка · {fmt(now, ctx.tz, '%H:%M')}")]
    return "\n".join(lines)


async def refresh(ctx, now: int, force: bool = False) -> None:
    """Doska yo'q bo'lsa — yoziladi va qadaladi; bor bo'lsa — o'zgargandagina tahrirlanadi."""
    db, n = ctx.db, ctx.notifier
    if not db.flag("board_on") or not db.flag("bot_enabled"):
        return
    try:
        gid = n.group_id()
    except Exception:
        return
    mono = time.monotonic()
    if mono < _state["pause"] and not force:
        return                                                   # Telegram «kuting» degan — kutamiz
    body = text(ctx, now)
    mid = db.get_int("board_msg_id")
    if mid and db.get("board_gid") == str(gid):
        if body == db.get("board_text") and not force:
            return
        if not force and mono - _state["edit"] < MIN_EDIT:
            return                                               # keyingi tekshiruvda (son baribir to'g'ri bo'ladi)
        _state["edit"] = mono
        try:
            await ctx.bot.edit_message_text(body, chat_id=gid, message_id=mid, parse_mode="HTML",
                                            disable_web_page_preview=True)
            db.set("board_text", body)
            return
        except Exception as exc:
            wait = getattr(exc, "retry_after", None)
            if wait:
                _state["pause"] = time.monotonic() + float(wait) + 1
                return
            low = str(exc).lower()
            if "not modified" in low:
                db.set("board_text", body)
                return
            if not any(k in low for k in ("not found", "can't be edited", "message to edit", "message_id_invalid")):
                log.info("Doska yangilanmadi: %s", exc)              # tarmoq va h.k. — keyingi safar
                return
            log.info("Doska o'chirilgan — qaytadan yoziladi")
    try:
        msg = await ctx.bot.send_message(chat_id=gid, text=body, parse_mode="HTML", disable_notification=True,
                                         disable_web_page_preview=True)
    except Exception as exc:
        wait = getattr(exc, "retry_after", None)
        if wait:
            _state["pause"] = time.monotonic() + float(wait) + 1
        else:
            log.info("Doska yozilmadi: %s", exc)
        return
    _state["edit"] = time.monotonic()
    db.set("board_msg_id", str(msg.message_id))
    db.set("board_gid", str(msg.chat.id))
    db.set("board_text", body)
    try:
        await ctx.bot.pin_chat_message(chat_id=msg.chat.id, message_id=msg.message_id, disable_notification=True)
    except Exception as exc:
        log.info("Doska qadalmadi: %s", exc)
        from .context import tr
        await n.notify_owner(lambda: (tr(
            "📌 «Задержки сейчас» «Проёб»ga yozildi, lekin qadab bo'lmadi. Botga guruhda «Xabarlarni qadash» "
            "huquqini bering: guruh → ✏️ → Administratorlar → bot.",
            "📌 «Задержки сейчас» отправлено в «Проёб», но закрепить не удалось. Дайте боту право «Закреплять "
            "сообщения»: группа → ✏️ → Администраторы → бот."), None), key="board-pin", min_interval=86400)


async def loop(ctx) -> None:
    """Alohida fon vazifasi: «задержка», eslatma va Push xabarlarini kutib qolmaydi."""
    from .alive import beat
    while True:
        beat("doska")                                            # 🫀 tiriklik
        await asyncio.sleep(EVERY)
        try:
            await refresh(ctx, int(ctx.clock()))
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Doska")


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
