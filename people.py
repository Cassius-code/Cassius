"""Xodimlar, papkalar, chatlar va adminlar: ro'yxatlar va qidiruv (bitta joyda)."""
from __future__ import annotations

import re
import time

from .db import Database

KASSA_KINDS = ("worker", "self", "partner", "pool")


def norm_username(raw: str | None) -> str:
    """'@Ivan', 't.me/Ivan', 'ivan' -> 'ivan'."""
    s = (raw or "").strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/"):
        if s.lower().startswith(prefix):
            s = s[len(prefix):]
    return s.lstrip("@").split("/")[0].split("?")[0].strip().lower()


def valid_username(u: str) -> bool:
    return bool(re.fullmatch(r"[a-z][a-z0-9_]{3,31}", u or ""))


# ───────────────────────── adminlar
def admin_level(db: Database, owners: tuple[int, ...], uid: int | None) -> str:
    """'owner' | 'full' | 'view' | ''."""
    if uid is None:
        return ""
    if uid in owners:
        return "owner"
    row = db.one("SELECT level FROM admins WHERE user_id=?", (uid,))
    return row["level"] if row else ""


def admins(db: Database):
    return db.all("SELECT * FROM admins ORDER BY (level='owner') DESC, added_ts")


def set_admin(db: Database, uid: int, level: str, name: str = "") -> None:
    db.run("INSERT INTO admins(user_id, level, name, added_ts) VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
           "level=excluded.level, name=CASE WHEN excluded.name<>'' THEN excluded.name ELSE admins.name END",
           (uid, level, name, int(time.time())))


def del_admin(db: Database, uid: int) -> None:
    db.run("DELETE FROM admins WHERE user_id=?", (uid,))


# ───────────────────────── xodimlar
def person(db: Database, pid: int | None):
    return db.one("SELECT * FROM people WHERE id=?", (pid,)) if pid else None


def people(db: Database, active_only: bool = True, kassa: bool | None = None, kinds=None):
    sql = "SELECT * FROM people WHERE 1=1"
    args: list = []
    if active_only:
        sql += " AND active=1"
    if kassa is True:
        sql += " AND kassa_kind<>''"
    elif kassa is False:
        sql += " AND kassa_kind=''"
    if kinds:
        sql += " AND kassa_kind IN (%s)" % ",".join("?" * len(kinds))
        args += list(kinds)
    sql += (" ORDER BY (kassa_kind='self') DESC, (kassa_kind='partner') ASC, (kassa_kind='pool') ASC, "
            "lower(name)")
    return db.all(sql, args)


def add_person(db: Database, name: str, username: str = "", tg_id: int | None = None,
               kassa_kind: str = "") -> int:
    cur = db.run("INSERT INTO people(name, username, tg_id, kassa_kind, created_ts) VALUES(?,?,?,?,?)",
                 (name.strip()[:40], norm_username(username), tg_id, kassa_kind, int(time.time())))
    return int(cur.lastrowid)


def update_person(db: Database, pid: int, **fields) -> None:
    allowed = {"name", "username", "tg_id", "active", "kassa_kind", "zp_on", "attend", "days_off"}
    for k, v in fields.items():
        if k in allowed:
            if k == "username":
                v = norm_username(v)
            db.run(f"UPDATE people SET {k}=? WHERE id=?", (v, pid))


def by_tg(db: Database, tg_id: int | None):
    return db.one("SELECT * FROM people WHERE tg_id=? ORDER BY active DESC, id LIMIT 1", (tg_id,)) if tg_id else None


def by_username(db: Database, username: str | None):
    u = norm_username(username)
    return db.one("SELECT * FROM people WHERE username=? ORDER BY active DESC, id LIMIT 1", (u,)) if u else None


def by_name(db: Database, name: str):
    return db.one("SELECT * FROM people WHERE lower(name)=lower(?) ORDER BY active DESC, id LIMIT 1", (name.strip(),))


def identify(db: Database, tg_id: int | None, username: str | None):
    """Yozgan odam — qaysi xodim? Telegram ID bo'yicha, bo'lmasa @username bo'yicha — va ID ni eslab qoladi
    (keyingi safar @username o'zgarsa ham taniydi). @username bir vaqtda faqat bitta akkauntda bo'ladi."""
    u = norm_username(username)
    p = by_tg(db, tg_id)
    if p is not None:
        if u and u != p["username"] and by_username(db, u) is None:
            db.run("UPDATE people SET username=? WHERE id=?", (u, p["id"]))
            p = person(db, p["id"])
        return p
    p = by_username(db, u)
    if p is not None and tg_id and p["tg_id"] != tg_id:
        db.run("UPDATE people SET tg_id=? WHERE id=?", (tg_id, p["id"]))
        p = person(db, p["id"])
    return p


def _key(s: str | None) -> str:
    return re.sub(r"[\W_]+", "", (s or "").casefold())


def twins(db: Database) -> list[tuple]:
    """Bitta odamning ikki yozuvi bo'lishi mumkin: kassadagi «Baxa» (💼) va nazoratdagi «@baxa» (👤). Ism yoki
    @username bir xil bo'lsa — [(kassa yozuvi, nazorat yozuvi)]. Bot ularni o'zi birlashtirmaydi — egasidan so'raydi."""
    out = []
    kassa = [p for p in people(db) if p["kassa_kind"] in ("worker", "self")]
    for c in people(db, kassa=False):
        keys = {_key(c["name"]), _key(c["username"])} - {""}
        hits = [k for k in kassa if keys & ({_key(k["name"]), _key(k["username"])} - {""})
                and (not k["tg_id"] or not c["tg_id"] or k["tg_id"] == c["tg_id"])
                and (not k["username"] or not c["username"] or k["username"] == c["username"])]
        if len(hits) == 1:
            out.append((hits[0], c))
    return out


def label(p) -> str:
    """Ism + @username (bo'lsa)."""
    if p is None:
        return "?"
    return p["name"] + (f" (@{p['username']})" if p["username"] and p["username"] != p["name"].lower() else "")


def mention(p) -> str:
    return f"@{p['username']}" if p and p["username"] else (p["name"] if p else "?")


def merge_people(db: Database, keep: int, drop: int) -> None:
    """Bitta odamning ikki yozuvini birlashtirish (masalan kassadan va nazoratdan kelgan)."""
    a, b = person(db, keep), person(db, drop)
    if a is None or b is None or keep == drop:
        return
    with db.tx():
        for col in ("username", "tg_id"):
            if not a[col] and b[col]:
                db.conn.execute(f"UPDATE people SET {col}=? WHERE id=?", (b[col], keep))
        if not a["kassa_kind"] and b["kassa_kind"]:
            db.conn.execute("UPDATE people SET kassa_kind=?, zp_on=? WHERE id=?", (b["kassa_kind"], b["zp_on"], keep))
            db.conn.execute("DELETE FROM pct WHERE person_id=?", (keep,))
            db.conn.execute("UPDATE pct SET person_id=? WHERE person_id=?", (keep, drop))
        db.conn.execute("DELETE FROM pct WHERE person_id=?", (drop,))
        db.conn.execute("INSERT OR IGNORE INTO folder_people(folder_id, person_id) "
                        "SELECT folder_id, ? FROM folder_people WHERE person_id=?", (keep, drop))
        db.conn.execute("DELETE FROM folder_people WHERE person_id=?", (drop,))
        for table, col in (("reports", "person_id"), ("checks", "pay"), ("adj", "person_id"), ("breaks", "person_id"),
                           ("transfers", "from_id"), ("transfers", "to_id"), ("shares", "from_id"),
                           ("shares", "to_id"), ("payouts", "person_id"), ("audit", "person_id"),
                           ("strikes", "person_id"), ("replies", "person_id"), ("cards", "person_id"),
                           ("roster", "person_id")):
            db.conn.execute(f"UPDATE {table} SET {col}=? WHERE {col}=?", (keep, drop))
        for table in ("attendance", "roster_off"):
            db.conn.execute(f"UPDATE OR IGNORE {table} SET person_id=? WHERE person_id=?", (keep, drop))
            db.conn.execute(f"DELETE FROM {table} WHERE person_id=?", (drop,))
        if not a["attend"] and b["attend"] and a["kassa_kind"] in ("", "worker"):
            db.conn.execute("UPDATE people SET attend=1 WHERE id=?", (keep,))
        if b["days_off"] and not a["days_off"]:
            db.conn.execute("UPDATE people SET days_off=? WHERE id=?", (b["days_off"], keep))
        db.conn.execute("DELETE FROM people WHERE id=?", (drop,))


def person_usage(db: Database, pid: int) -> dict:
    """O'chirishdan oldin: shu odamga bog'liq kassa yozuvlari soni."""
    return {"checks": db.scalar("SELECT COUNT(*) FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE r.person_id=?",
                                (pid,)),
            "adj": db.scalar("SELECT COUNT(*) FROM adj WHERE person_id=?", (pid,)),
            "worked": db.scalar("SELECT COUNT(*) FROM checks WHERE pay=?", (pid,)),
            "payouts": db.scalar("SELECT COUNT(*) FROM payouts WHERE person_id=?", (pid,))}


def delete_person(db: Database, pid: int) -> None:
    """Xodimni butunlay o'chirish: uning akkaunt cheklari, jarima/bonus/avans, foizlari, papkalari ham."""
    with db.tx():
        c = db.conn
        rids = [r[0] for r in c.execute("SELECT id FROM reports WHERE person_id=?", (pid,))]
        for rid in rids:
            c.execute("DELETE FROM checks WHERE report_id=?", (rid,))
        c.execute("DELETE FROM reports WHERE person_id=?", (pid,))
        c.execute("UPDATE checks SET pay=NULL WHERE pay=?", (pid,))
        for table, col in (("adj", "person_id"), ("pct", "person_id"), ("folder_people", "person_id"),
                           ("attendance", "person_id"), ("breaks", "person_id"), ("transfers", "from_id"),
                           ("transfers", "to_id"), ("shares", "from_id"), ("shares", "to_id"),
                           ("payouts", "person_id"), ("owner_pct", "acct"), ("strikes", "person_id"),
                           ("roster", "person_id"), ("roster_off", "person_id")):
            c.execute(f"DELETE FROM {table} WHERE {col}=?", (pid,))
        c.execute("DELETE FROM people WHERE id=?", (pid,))


def wipe(db: Database, what: str) -> None:
    """🧹 Tozalash: kassa | people (kassa ham) | push. Prays, sozlamalar, papkalar, chatlar, adminlar qoladi."""
    with db.tx():
        c = db.conn
        if what in ("kassa", "people", "all"):
            for t in ("checks", "reports", "adj", "transfers", "shares", "payouts", "audit", "closed_days", "weeks",
                      "owner_pct", "strikes"):
                c.execute(f"DELETE FROM {t}")
            c.execute("DELETE FROM requests WHERE kind='zp'")
        if what in ("people", "all"):
            for t in ("people", "pct", "folder_people", "attendance", "breaks", "roster", "roster_off"):
                c.execute(f"DELETE FROM {t}")
        if what in ("push", "all"):
            c.execute("DELETE FROM accounts")
            c.execute("UPDATE folders SET push_account_id=NULL")


def is_day_off(p, weekday: int) -> bool:
    return str(weekday) in (p["days_off"] or "")


# ───────────────────────── papkalar
def folders(db: Database):
    return db.all("SELECT * FROM folders ORDER BY lower(name)")


def folder(db: Database, fid: int | None):
    return db.one("SELECT * FROM folders WHERE id=?", (fid,)) if fid else None


def add_folder(db: Database, name: str) -> int | None:
    name = name.strip()[:40]
    if not name or db.one("SELECT 1 FROM folders WHERE name_key=?", (name.casefold(),)):
        return None
    return int(db.run("INSERT INTO folders(name, name_key) VALUES(?,?)", (name, name.casefold())).lastrowid)


def rename_folder(db: Database, fid: int, name: str) -> bool:
    name = name.strip()[:40]
    if not name or db.one("SELECT 1 FROM folders WHERE name_key=? AND id<>?", (name.casefold(), fid)):
        return False
    db.run("UPDATE folders SET name=?, name_key=? WHERE id=?", (name, name.casefold(), fid))
    return True


def delete_folder(db: Database, fid: int) -> None:
    with db.tx():
        db.conn.execute("DELETE FROM folder_people WHERE folder_id=?", (fid,))
        db.conn.execute("DELETE FROM chats WHERE folder_id=?", (fid,))
        db.conn.execute("DELETE FROM folders WHERE id=?", (fid,))


def set_folder(db: Database, fid: int, **fields) -> None:
    allowed = {"delay_on", "fine_usd", "push_on", "push_account_id", "push_limit", "quiet_from", "quiet_to"}
    for k, v in fields.items():
        if k in allowed:
            db.run(f"UPDATE folders SET {k}=? WHERE id=?", (v, fid))


def folder_people(db: Database, fid: int):
    return db.all("SELECT p.* FROM people p JOIN folder_people fp ON fp.person_id=p.id "
                  "WHERE fp.folder_id=? AND p.active=1 ORDER BY lower(p.name)", (fid,))


def person_folders(db: Database, pid: int):
    return db.all("SELECT f.* FROM folders f JOIN folder_people fp ON fp.folder_id=f.id WHERE fp.person_id=? "
                  "ORDER BY lower(f.name)", (pid,))


def toggle_folder_person(db: Database, fid: int, pid: int) -> bool:
    if db.one("SELECT 1 FROM folder_people WHERE folder_id=? AND person_id=?", (fid, pid)):
        db.run("DELETE FROM folder_people WHERE folder_id=? AND person_id=?", (fid, pid))
        return False
    db.run("INSERT INTO folder_people(folder_id, person_id) VALUES(?,?)", (fid, pid))
    return True


# ───────────────────────── chatlar
def chats(db: Database, fid: int | None = None):
    if fid is None:
        return db.all("SELECT * FROM chats ORDER BY title")
    return db.all("SELECT * FROM chats WHERE folder_id=? ORDER BY title", (fid,))


def chat_folder_map(db: Database) -> dict[int, int]:
    return {r["chat_id"]: r["folder_id"] for r in db.all("SELECT chat_id, folder_id FROM chats")}


def sync_folder_chats(db: Database, fid: int, ids: set[int]) -> tuple[int, int]:
    """Telegram papkasidagi chatlar ro'yxati bilan moslash (qo'lda qo'shilganlar saqlanadi)."""
    have = {r["chat_id"]: r["source"] for r in db.all("SELECT chat_id, source FROM chats WHERE folder_id=?", (fid,))}
    added = removed = 0
    for cid in ids:
        if cid not in have:
            other = db.one("SELECT folder_id FROM chats WHERE chat_id=?", (cid,))
            if other is None:
                db.run("INSERT INTO chats(chat_id, folder_id, source) VALUES(?,?, 'sync')", (cid, fid))
                added += 1
    for cid, src in have.items():
        if src == "sync" and cid not in ids:
            db.run("DELETE FROM chats WHERE chat_id=?", (cid,))
            removed += 1
    return added, removed
