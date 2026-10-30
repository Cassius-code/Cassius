"""🔒 Panel qulfi (egasi bilan kelishilgan, 2026-10-30).

* Ega bosh menyuda «🔒 Qulflash» bosadi — faqat SHU akkauntdagi panel yopiladi (ikkinchi ega akkaunti ishlayveradi).
  Bot o'z ishini davom ettiradi: zaderjka, jarima, Push, «Проёб» — faqat panel yopiq.
* Qulf paytida shu chatda nima qilinsa ham (/start, tugma, matn) — faqat «Бот сейчас не работает.» (doim ruscha).
* To'g'ri kod yozilsa — panel qaytadi va qulf paytida kutib turgan xabarlar keladi. Xato kod — o'sha matn turaveradi
  (cheklov yo'q — egasi tanlagan). Yozilgan kod chatdan darhol o'chadi.
* Kod hamma ega akkauntlari uchun bitta (⚙️ → 👮 Adminlar → 🔒 Qulf kodi). Bazada faqat izi (PBKDF2, tuz bilan)."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import time

from . import ui
from .ui import Req, card, kb, on_input, screen, title

DECOY = "Бот сейчас не работает."
MIN_LEN = 4
MAX_LEN = 32
ITER = 100_000


def _hash(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.strip().encode(), salt, ITER)


def is_set(db) -> bool:
    return bool(db.get("lock_hash"))


def set_code(db, code: str) -> None:
    salt = os.urandom(16)
    db.set("lock_hash", salt.hex() + ":" + _hash(code, salt).hex())
    db.set("lock_code_ts", str(int(time.time())))


def matches(db, code: str) -> bool:
    raw = db.get("lock_hash")
    if not raw or ":" not in raw or not code or len(code.strip()) > MAX_LEN:
        return False
    salt_hex, want = raw.split(":", 1)
    return hmac.compare_digest(_hash(code, bytes.fromhex(salt_hex)).hex(), want)


def locked(db, uid: int | None) -> bool:
    return bool(uid) and db.get(f"lock:{uid}") == "1"


async def show_decoy(ctx, chat_id: int, fresh: bool = True) -> None:
    """Panel o'rnida faqat «Бот сейчас не работает.» (tugmasiz). Chatda doim bitta xabar."""
    ui.WAIT.pop(chat_id, None)
    await ui.show(ctx.bot, chat_id, DECOY, None, fresh=fresh, view=None)


async def try_unlock(ctx, uid: int, chat_id: int, text: str) -> bool:
    """Qulflangan ega yozdi: kod to'g'rimi? To'g'ri — qulf ochiladi, kutib turgan xabarlar keladi, panel qaytadi."""
    if not await asyncio.to_thread(matches, ctx.db, text or ""):
        return False
    ctx.db.set(f"lock:{uid}", "0")
    await ctx.notifier.release(uid)                         # qulf paytida kelgan xabarlar — endi
    from .panel import main_menu, make_req
    req = make_req(ctx, uid, chat_id, "m")
    text_, markup = await main_menu(ctx, req)
    ui.HIST.pop(uid, None)
    await ui.show(ctx.bot, chat_id, text_, markup, fresh=True, view="m")
    return True


@screen("lk", "owner")
async def lock_now(ctx, r: Req):
    """🔒 Qulflash: kod qo'yilmagan bo'lsa — avval kod; bo'lsa — shu akkaunt darhol qulflanadi."""
    if not is_set(ctx.db):
        return await code_screen(ctx, r, then_lock=True)
    ctx.db.set(f"lock:{r.uid}", "1")
    ui.HIST.pop(r.uid, None)
    await show_decoy(ctx, r.chat_id, fresh=False)
    return None


@screen("lkc", "owner")
async def code_screen(ctx, r: Req, then_lock: bool = False):
    """🔒 Qulf kodini qo'yish / almashtirish (hamma ega akkauntlari uchun bitta)."""
    then_lock = then_lock or (bool(r.args) and r.args[0] == "lock")
    ui.ask(r, "lock_code", "m" if then_lock else "sd", lock=then_lock)
    ts = ctx.db.get("lock_code_ts")
    state = (r.L(f"Hozir: o'rnatilgan ({time.strftime('%d.%m.%Y', time.localtime(int(ts)))})",
                 f"Сейчас: задан ({time.strftime('%d.%m.%Y', time.localtime(int(ts)))})")
             if is_set(ctx.db) and ts else r.L("Hozir: yo'q", "Сейчас: нет"))
    lines = [r.L("«🔒 Qulflash» bosilsa, shu akkauntda panel o'rniga faqat «Бот сейчас не работает.» chiqadi. "
                 "Ochish uchun botga shu kodni yozasiz — panel qaytadi, qulf paytidagi xabarlar keladi.",
                 "После «🔒 Заблокировать» в этом аккаунте вместо панели — только «Бот сейчас не работает.». "
                 "Чтобы открыть, напишите боту этот код — панель вернётся, придут сообщения за время блокировки."),
             r.L("Kod hamma ega akkauntlari uchun bitta. Bot ishlashda davom etadi (zaderjka, Push, «Проёб»).",
                 "Код один для всех аккаунтов владельца. Бот продолжает работать (задержки, Пуш, «Проёб»)."),
             "",
             r.L(f"Kodni yuboring: {MIN_LEN}–{MAX_LEN} belgi, bo'sh joysiz. Uzunroq kod — xavfsizroq. Xabaringiz darhol "
                 "o'chadi, bazada faqat shifrlangan izi qoladi.",
                 f"Пришлите код: {MIN_LEN}–{MAX_LEN} символов, без пробелов. Длиннее — надёжнее. Сообщение сразу "
                 "удалится, в базе — только зашифрованный след."),
             state]
    return ui.join(title("🔒", r.L("QULF KODI", "КОД БЛОКИРОВКИ")), "", card(lines)), \
        kb([(r.L("✖️ Bekor qilish", "✖️ Отмена"), "m" if then_lock else "sd")])


@on_input("lock_code", "owner")
async def code_set(ctx, r: Req, lock: bool = False):
    code = (r.message.text if r.message is not None and getattr(r.message, "text", None) else r.text).strip()
    if not MIN_LEN <= len(code) <= MAX_LEN or any(ch.isspace() for ch in code):
        return r.L(f"⚠️ {MIN_LEN}–{MAX_LEN} belgi, bo'sh joysiz", f"⚠️ {MIN_LEN}–{MAX_LEN} символов, без пробелов")
    await asyncio.to_thread(set_code, ctx.db, code)
    await ui.toast(ctx.bot, r.chat_id, r.L("✅ Qulf kodi saqlandi", "✅ Код блокировки сохранён"))
    if lock:
        ctx.db.set(f"lock:{r.uid}", "1")
        ui.WAIT.pop(r.uid, None)
        ui.HIST.pop(r.uid, None)
        await show_decoy(ctx, r.chat_id, fresh=False)
        return None
    from .panel_settings import admins
    r.args = []
    ui.view(r, "sd")
    return await admins(ctx, r)
