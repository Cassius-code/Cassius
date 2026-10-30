"""📅 Bugun kim qayerda: har RD da shu kuni kim ishlaydi (egasi: «1 ta RD da bitta xodim ishlaydi»).

Asos — xodimning papkalari (👥 → ⚙️ → 📁) va haftalik dam olish kunlari (🛌). Shu kunga alohida:
* «Baxa bugun ishlamaydi» (roster_off) — o'z RD laridan chiqadi;
* «RD 5 ga bugun Aziza qarasin» (roster) — shu kuni shu RD ning xodimi Aziza (odatdagisi o'rniga).
Belgilash («задержка», «ставка», eslatmalar), jarima, ishga kelish va papka akkauntidan yozgan xodimni tanish —
hammasi shu ro'yxat bo'yicha. Dam olayotgan xodim belgilanmaydi va jarima olmaydi."""
from __future__ import annotations

import datetime as dt
import time

from . import people as P


def _iso(day) -> str:
    return day.isoformat() if hasattr(day, "isoformat") else str(day)


def regular(db, fid: int) -> list:
    """Papkaning doimiy xodimlari (👥 → 📁)."""
    return P.folder_people(db, fid)


def override(db, fid: int, day):
    """Shu kunga alohida belgilangan xodim (yoki None)."""
    row = db.one("SELECT person_id FROM roster WHERE day=? AND folder_id=?", (_iso(day), fid))
    return P.person(db, row["person_id"]) if row else None


def marked_off(db, pid: int, day) -> bool:
    return db.one("SELECT 1 FROM roster_off WHERE day=? AND person_id=?", (_iso(day), pid)) is not None


def resting(db, p, day) -> bool:
    """Shu kuni o'z RD larida ishlamaydi: haftalik dam olish kuni yoki «bugun ishlamaydi»."""
    d = day if hasattr(day, "weekday") else dt.date.fromisoformat(str(day))
    return marked_off(db, p["id"], d) or P.is_day_off(p, d.weekday())


def workers(db, fid: int | None, day) -> list:
    """Shu kuni shu RD da ishlaydigan xodim(lar). Odatda bitta."""
    if not fid:
        return []
    ov = override(db, fid, day)
    if ov is not None:
        return [ov] if ov["active"] else []
    return [p for p in regular(db, fid) if not resting(db, p, day)]


def main_worker(db, fid: int | None, day):
    w = workers(db, fid, day)
    return w[0] if w else None


def person_rds(db, pid: int, day) -> list:
    """Xodim shu kuni qaysi RD larda ishlaydi."""
    return [f for f in P.folders(db) if any(p["id"] == pid for p in workers(db, f["id"], day))]


def works(db, p, day) -> bool:
    return bool(person_rds(db, p["id"], day))


def day_off_people(db, day) -> list:
    """Shu kuni dam olayotganlar (doimiy RD si bor, lekin bugun hech qayerda ishlamaydi)."""
    out = []
    for p in P.people(db):
        if P.person_folders(db, p["id"]) and resting(db, p, day) and not person_rds(db, p["id"], day):
            out.append(p)
    return out


# ───────────────────────── o'zgartirish (faqat shu kun uchun)
def set_off(db, pid: int, day, off: bool = True) -> None:
    """«Bugun ishlamaydi» — yoki qaytarish. Ishlamaydigan xodim boshqa RD ga ham qo'yilmagan bo'ladi."""
    d = _iso(day)
    if off:
        db.run("INSERT OR REPLACE INTO roster_off(day, person_id, ts) VALUES(?,?,?)", (d, pid, int(time.time())))
        db.run("DELETE FROM roster WHERE day=? AND person_id=?", (d, pid))
    else:
        db.run("DELETE FROM roster_off WHERE day=? AND person_id=?", (d, pid))


def assign(db, fid: int, pid: int, day) -> None:
    """Shu kuni RD ga shu xodim (odatdagisi o'rniga). U «ishlamaydi» bo'lsa — endi ishlaydi."""
    d = _iso(day)
    db.run("INSERT OR REPLACE INTO roster(day, folder_id, person_id, ts) VALUES(?,?,?,?)", (d, fid, pid, int(time.time())))
    db.run("DELETE FROM roster_off WHERE day=? AND person_id=?", (d, pid))


def reset(db, fid: int, day) -> None:
    """RD — odatdagidek (doimiy xodimi)."""
    db.run("DELETE FROM roster WHERE day=? AND folder_id=?", (_iso(day), fid))


def empty_rds(db, day) -> list:
    """Nazoratdagi RD lardan shu kuni hech kim ishlamaydiganlari."""
    return [f for f in P.folders(db) if f["delay_on"] and not workers(db, f["id"], day)
            and db.one("SELECT 1 FROM chats WHERE folder_id=? LIMIT 1", (f["id"],))]
