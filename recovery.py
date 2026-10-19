"""🔐 Tiklash kodi: ega akkaunti yo'qolsa — yangi Telegram akkauntdan botga «/ega KOD» yozib ega bo'lish.

* Kodni ega o'zi o'rnatadi (⚙️ → 👮 Adminlar → 🔐 Tiklash kodi). Bazada faqat xeshi saqlanadi (PBKDF2, tuz bilan).
* Kod bir marta ishlaydi: ishlatilgach o'chadi, yangi ega yangisini o'rnatadi.
* Noto'g'ri urinish: bir odamga kuniga 5 ta, hammaga kuniga 20 ta. Har urinish va muvaffaqiyat egalarga xabar qilinadi.
* Xabar (kod bilan) chatdan darhol o'chiriladi.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import os
import time

from . import people as P

MIN_LEN = 8
ITER = 200_000
USER_LIMIT = 5
ALL_LIMIT = 20


def _hash(code: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.strip().encode(), salt, ITER)


def is_set(db) -> bool:
    return bool(db.get("recovery_hash"))


def set_code(db, code: str) -> None:
    salt = os.urandom(16)
    db.set("recovery_hash", salt.hex() + ":" + _hash(code, salt).hex())
    db.set("recovery_ts", str(int(time.time())))


def clear(db) -> None:
    db.set("recovery_hash", "")
    db.set("recovery_ts", "")


def matches(db, code: str) -> bool:
    raw = db.get("recovery_hash")
    if not raw or ":" not in raw:
        return False
    salt_hex, want = raw.split(":", 1)
    return hmac.compare_digest(_hash(code, bytes.fromhex(salt_hex)).hex(), want)


def _count(db, key: str, day: str) -> int:
    v = db.get(key)
    d, _, n = v.partition(":")
    return int(n) if d == day and n.isdigit() else 0


async def try_code(ctx, uid: int, name: str, code: str) -> tuple[str, str]:
    """-> (natija, egalarga xabar). natija: ok | already | none | limit | bad | short."""
    db = ctx.db
    if P.admin_level(db, ctx.cfg.owner_ids, uid) == "owner":
        return "already", ""
    if not is_set(db):
        return "none", ""
    day = time.strftime("%Y-%m-%d")
    ukey, akey = f"recovery_fail:{uid}", "recovery_fail:all"
    if _count(db, ukey, day) >= USER_LIMIT or _count(db, akey, day) >= ALL_LIMIT:
        return "limit", ""
    code = (code or "").strip()
    name = html.escape(name, quote=False)
    if len(code) < MIN_LEN or not await asyncio.to_thread(matches, db, code):
        db.set(ukey, f"{day}:{_count(db, ukey, day) + 1}")
        db.set(akey, f"{day}:{_count(db, akey, day) + 1}")
        return "bad", f"⚠️ <b>Tiklash kodi noto'g'ri kiritildi</b>\n👤 {name} · <code>{uid}</code>"
    P.set_admin(db, uid, "owner", name)
    clear(db)
    return "ok", (f"🔐 <b>Tiklash kodi ishlatildi</b>\n👤 {name} · <code>{uid}</code> endi 👑 ega.\n"
                  "Kod o'chirildi — yangisini o'rnating: ⚙️ → 👮 Adminlar → 🔐 Tiklash kodi.")
