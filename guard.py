"""🛡 Push akkauntlarini himoya: kuniga bir marta @SpamBot dan so'raladi. Telegram cheklov qo'ygan bo'lsa — o'sha
akkauntdan Push to'xtaydi (akkaunt ulanib turadi va har kuni qayta tekshiriladi), egaga xabar boradi. Cheklov olinsa —
Push o'zi qaytadi.

@SpamBot — Telegram'ning rasmiy boti; uning javobidan faqat «cheklov bormi» degani olinadi.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from .accounts import MAIN

log = logging.getLogger("guard")

OK_WORDS = ("no limits", "free as a bird", "good news", "свобод", "хорошие новости", "ограничений нет")
BAD_WORDS = ("limited", "restricted", "unfortunately", "ограничен", "к сожалению", "заблокир")
CHECK_HOUR = 9                 # har kuni shu soatdan keyin (Toshkent) bir marta


def verdict(text: str) -> str:
    """@SpamBot javobi -> 'ok' | 'limited' | '' (tushunilmadi — hech narsa o'zgartirilmaydi)."""
    t = (text or "").lower()
    if any(w in t for w in OK_WORDS):
        return "ok"
    if any(w in t for w in BAD_WORDS):
        return "limited"
    return ""


async def ask_spambot(client, wait: float = 15.0, step: float = 1.5) -> str:
    sent = await client.send_message("SpamBot", "/start")
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        await asyncio.sleep(step)
        for m in await client.get_messages("SpamBot", limit=3):
            if int(m.id) > int(sent.id) and not m.out:
                return verdict(m.message or "")
    return ""


def state(db, acc_id: int) -> str:
    if acc_id == MAIN:
        return db.get("main_spam")
    row = db.one("SELECT spam FROM accounts WHERE id=?", (acc_id,))
    return row["spam"] if row else ""


def _name(db, acc_id: int) -> str:
    if acc_id == MAIN:
        return "🔑"
    row = db.one("SELECT name, label FROM accounts WHERE id=?", (acc_id,))
    return f"{row['name']} {row['label']}".strip() if row else f"#{acc_id}"


async def apply(ctx, acc_id: int, new: str, now: int) -> None:
    """Natijani yozish; holat o'zgarsa — egaga xabar."""
    db = ctx.db
    old = state(db, acc_id)
    if acc_id == MAIN:
        db.set("main_spam", new)
        db.set("main_spam_ts", str(now))
    else:
        db.run("UPDATE accounts SET spam=?, spam_ts=? WHERE id=?", (new, now, acc_id))
    if new == old:
        return
    from .context import tr
    name = _name(db, acc_id)
    main_uz, main_ru = ("Asosiy akkaunt", "Основной аккаунт") if acc_id == MAIN else (name, name)
    if new == "limited":
        text = (lambda: (tr(f"🛡 <b>{main_uz}</b>: Telegram spam-cheklov qo'ygan (@SpamBot). Bu akkauntdan Push "
                            "to'xtatildi. Har kuni qayta tekshiriladi — cheklov olinsa, o'zi yoqiladi.",
                            f"🛡 <b>{main_ru}</b>: Telegram наложил спам-ограничение (@SpamBot). Пуш с этого аккаунта "
                            "остановлен. Проверка каждый день — когда снимут, включится сам."), None))
    elif old == "limited":
        text = (lambda: (tr(f"🛡 <b>{main_uz}</b>: cheklov olindi — Push yana yoqildi.",
                            f"🛡 <b>{main_ru}</b>: ограничение снято — Пуш снова включён."), None))
    else:
        return
    try:
        await ctx.notifier.notify_owner(text, key=f"spam-{acc_id}")
    except Exception:
        log.exception("Spam xabari yuborilmadi")


def targets(ctx) -> list[tuple[int, object]]:
    out = [(acc_id, acc) for acc_id, acc in (ctx.pool.accounts.items() if ctx.pool else [])
           if acc.state == "online" and acc.client is not None]
    ub = ctx.userbot
    if ub is not None and ub.state == "online" and ub.client is not None \
            and ctx.db.one("SELECT 1 FROM folders WHERE push_account_id=?", (MAIN,)):
        out.append((MAIN, ub))                             # asosiy akkaunt ham Push qilsa
    return out


async def check_all(ctx, now: int) -> int:
    """Hamma Push akkauntlarni tekshirish. -> nechtasi tekshirildi."""
    n = 0
    for acc_id, acc in targets(ctx):
        try:
            v = await asyncio.wait_for(ask_spambot(acc.client), 40)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.info("@SpamBot tekshiruvi %s: %s", acc_id, type(exc).__name__)
            continue
        if v:
            await apply(ctx, acc_id, v, now)
            n += 1
        await asyncio.sleep(2)
    return n


async def daily(ctx, now: int) -> None:
    db = ctx.db
    if not db.flag("spam_check") or not db.flag("bot_enabled"):
        return
    t = datetime.fromtimestamp(now, ctx.tz)
    key = t.date().isoformat()
    if t.hour < CHECK_HOUR or db.get("spam_check_last") >= key:
        return
    db.set("spam_check_last", key)
    await check_all(ctx, now)
