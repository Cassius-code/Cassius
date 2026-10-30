"""Eski botlardan ma'lumot ko'chirish (bir marta).

1) Eski zaderjka/Push boti (tgcontrol): o'sha Railway Volume'dagi /data/tgcontrol.sqlite3 — ishga tushganda avtomat.
   Ko'chadi: sozlamalar, asosiy va Push akkauntlar (qayta kirish shart emas), papkalar, chatlar, topiklar, xodimlar,
   adminlar, shablonlar, lidlar (Push uchun), stavka holati. Eski zaderjkalar ko'chmaydi — nazorat yangidan boshlanadi.
2) Kassa boti: egasi yuborgan kassa.db fayli (⚙️ Sozlamalar → 📥). Ko'chadi: xodimlar va foizlar, narxlar, cheklar,
   jarima/bonus/avanslar, o'tkazmalar, ulushlar, foydalanuvchilar (adminlar va xodim Telegram ID lari).
"""
from __future__ import annotations

import json

import logging
import sqlite3
import time
from pathlib import Path

from . import people as P

log = logging.getLogger("migrate")

SAME_KEYS = ("lang", "limit_minutes", "work_start", "work_end", "proyob_group_id", "skip_emojis", "break_minutes",
             "breaks_per_day", "breaks_enabled", "bot_enabled", "delay_enabled", "push_enabled", "push_emojis",
             "push_limit", "push_speed", "push_newlead_minutes", "push_quiet_from", "push_quiet_to", "push_from",
             "push_to", "push_media", "push_text", "push_idle_minutes",
             "report_time", "userbot_session", "track_from")
RENAMED = {"botwatch_enabled": "stavka_enabled", "botwatch_count": "stavka_count",
           "botwatch_cap": "stavka_cap"}


def _open(path) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _tables(con) -> set[str]:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _cols(con, table: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}


def _rows(con, table: str):
    return con.execute(f"SELECT * FROM {table}").fetchall() if table in _tables(con) else []


def _g(row, key, default=None):
    try:
        v = row[key]
    except (IndexError, KeyError):
        return default
    return default if v is None else v


def detect(path) -> str:
    """Fayl turi: 'kassa' (kassa boti), 'old' (eski zaderjka boti), 'new' (shu botning nusxasi) yoki ''."""
    try:
        con = _open(path)
    except sqlite3.Error:
        return ""
    try:
        t = _tables(con)
    except sqlite3.Error:
        return ""
    finally:
        con.close()
    if "workers" in t and "checks" in t:
        return "kassa"
    if "thread_state" in t and "employees" in t:
        return "old"
    if "threads" in t and "people" in t:
        return "new"
    return ""


# ═════════════════════════ 1) eski zaderjka/Push boti
def import_old(db, path: str | Path, now: int | None = None) -> dict:
    now = int(time.time() if now is None else now)
    con = _open(path)
    st: dict[str, int] = {}
    try:
        with db.tx():
            st.update(_old_settings(db, con, now))
            st.update(_old_structure(db, con))
            st.update(_old_threads(db, con, now))
        db._cache.clear()
    finally:
        con.close()
    db.set("old_imported", time.strftime("%Y-%m-%d %H:%M", time.localtime(now)))
    return st


def _old_settings(db, con, now: int) -> dict:
    old = {r["key"]: r["value"] for r in _rows(con, "settings")}
    n = 0
    for k in SAME_KEYS:
        if k in old and old[k] != "":
            db.run("INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (k, old[k]))
            n += 1
    for k, new in RENAMED.items():
        if k in old and old[k] != "":
            db.run("INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                   (new, old[k]))
            n += 1
    try:
        if int(old.get("push_repeat_minutes") or 0) > 0:
            db.run("INSERT OR REPLACE INTO settings(key, value) VALUES('push_repeat_minutes', ?)",
                   (old["push_repeat_minutes"],))
    except ValueError:
        pass
    # zaderjka va stavka — faqat yangi bot ishga tushgan paytdan (eski noto'g'ri signallar takrorlanmasin)
    db.run("INSERT OR REPLACE INTO settings(key, value) VALUES('delay_from', ?)", (str(now),))
    return {"sozlama": n}


def _old_structure(db, con) -> dict:
    st = {}
    # akkauntlar (id saqlanadi — papkalar shu id ga bog'langan)
    n = 0
    for a in _rows(con, "accounts"):
        db.run("INSERT OR REPLACE INTO accounts(id, name, session, user_id, label, paused, added_ts) "
               "VALUES(?,?,?,?,?,?,?)", (a["id"], a["name"], _g(a, "session", ""), _g(a, "user_id"),
                                         _g(a, "label", ""), _g(a, "paused", 0), _g(a, "added_ts", 0)))
        n += 1
    st["Push akkaunt"] = n
    # papkalar
    n = 0
    for f in _rows(con, "folders"):
        db.run("INSERT OR REPLACE INTO folders(id, name, name_key, delay_on, fine_usd, push_on, push_account_id, "
               "push_limit, quiet_from, quiet_to) VALUES(?,?,?,?,0,?,?,?,?,?)",
               (f["id"], f["name"], f["name_key"], _g(f, "delay_on", 1), _g(f, "push_on", 1), _g(f, "account_id"),
                _g(f, "push_limit", 0), _g(f, "quiet_from", ""), _g(f, "quiet_to", "")))
        n += 1
    st["papka"] = n
    n = 0
    for c in _rows(con, "chats"):
        db.run("INSERT OR REPLACE INTO chats(chat_id, folder_id, title, is_forum, source) VALUES(?,?,?,?,?)",
               (c["chat_id"], c["folder_id"], _g(c, "title", ""), _g(c, "is_forum", 0), _g(c, "source", "sync")))
        n += 1
    st["chat"] = n
    for t in _rows(con, "topics"):
        db.run("INSERT OR IGNORE INTO topics(chat_id, topic_id, title, icon) VALUES(?,?,?,?)",
               (t["chat_id"], t["topic_id"], _g(t, "title", ""), _g(t, "icon", "")))
    for e in _rows(con, "emoji_cache"):
        db.run("INSERT OR IGNORE INTO emoji_cache(doc_id, ch) VALUES(?,?)", (e["doc_id"], e["ch"]))
    # xodimlar: eski botda papka + @username → bitta odam bir nechta papkada bo'lishi mumkin
    n = 0
    for e in _rows(con, "employees"):
        u = P.norm_username(e["username"])
        if not u:
            continue
        p = P.by_username(db, u) or (P.by_tg(db, _g(e, "user_id")) if _g(e, "user_id") else None)
        pid = p["id"] if p else P.add_person(db, u, u, _g(e, "user_id"))
        if p is None:
            n += 1
        elif _g(e, "user_id") and not p["tg_id"]:
            db.run("UPDATE people SET tg_id=? WHERE id=?", (e["user_id"], pid))
        db.run("INSERT OR IGNORE INTO folder_people(folder_id, person_id) VALUES(?,?)", (e["folder_id"], pid))
    st["xodim"] = n
    for h in _rows(con, "people"):
        db.run("INSERT OR IGNORE INTO known_humans(user_id, name) VALUES(?,?)", (h["user_id"], _g(h, "name", "")))
    n = 0
    for a in _rows(con, "admins"):
        level = "view" if _g(a, "role", "view") == "view" else "full"
        if db.one("SELECT 1 FROM admins WHERE user_id=?", (a["user_id"],)) is None:
            db.run("INSERT INTO admins(user_id, level, name, added_ts) VALUES(?,?,?,?)",
                   (a["user_id"], level, "", _g(a, "added_ts", 0)))
            n += 1
    st["admin"] = n
    from . import push_lib as L
    for t in _rows(con, "templates"):
        db.run("INSERT INTO templates(name, text, media) VALUES(?,?,?)", (t["name"], _g(t, "text", ""),
                                                                           _g(t, "media", "")))
        try:                                               # 📚 kutubxonaga ham (aynan bir xili bo'lsa — qo'shilmaydi)
            m = json.loads(_g(t, "media", "") or "null")
        except ValueError:
            m = None
        if (_g(t, "text", "") or "").strip() or m:
            if L.same_as(db, L.fingerprint(_g(t, "text", ""), m), 0) is None:
                L.create(db, _g(t, "text", ""), m if isinstance(m, dict) else None, note=t["name"])
    return st


def _old_threads(db, con, now: int) -> dict:
    cap = db.get_int("stavka_cap", 180) * 60
    state = {(s["chat_id"], s["topic_id"]): s for s in _rows(con, "thread_state")}
    lead_cols = _cols(con, "leads") if "leads" in _tables(con) else set()
    bets_last: dict = {}
    for b in _rows(con, "bets"):
        db.run("INSERT OR IGNORE INTO bets(chat_id, topic_id, msg_id, ts) VALUES(?,?,?,?)",
               (b["chat_id"], b["topic_id"], b["msg_id"], b["ts"]))
        k = (b["chat_id"], b["topic_id"])
        bets_last[k] = max(bets_last.get(k, 0), b["ts"])
    n = 0
    seen = set()
    for ld in _rows(con, "leads"):
        k = (ld["chat_id"], ld["topic_id"])
        seen.add(k)
        s = state.get(k)
        sf = _g(ld, "stavka_from") if "stavka_from" in lead_cols else None
        se = _g(ld, "stavka_end") if "stavka_end" in lead_cols else None
        stavka = ""
        if sf:
            stavka = "on" if (se is None and now - sf < cap) else "done"
            if stavka == "done" and se is None:
                se = now
        db.run("INSERT OR REPLACE INTO threads(chat_id, topic_id, first_seen, last_seen, last_activity, msg_count, "
               "seen_msg_id, stavka, stavka_from, bets, bet_last_ts, stavka_end, stavka_reminded, last_push_ts) "
               "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,9,?)",          # 9: ko‘chirilgan stavkaga eslatma yubormaymiz
               (k[0], k[1], ld["first_seen"], ld["last_seen"], _g(ld, "last_activity_ts", 0), _g(ld, "msg_count", 0),
                _g(s, "seen_msg_id", 0) if s is not None else 0, stavka, sf, _g(ld, "bet_count", 0),
                bets_last.get(k), se, _g(ld, "last_push_ts")))
        n += 1
    for k, s in state.items():                    # lidsiz nitlar: faqat qayerda to'xtaganimiz
        if k not in seen and _g(s, "seen_msg_id"):
            db.run("INSERT OR IGNORE INTO threads(chat_id, topic_id, seen_msg_id) VALUES(?,?,?)",
                   (k[0], k[1], s["seen_msg_id"]))
    for i in _rows(con, "ignored_msgs"):
        db.run("INSERT OR IGNORE INTO ignored_msgs(chat_id, msg_id, ts) VALUES(?,?,?)", (i["chat_id"], i["msg_id"],
                                                                                          i["ts"]))
    return {"lid": n}


# ═════════════════════════ 2) kassa boti
def import_kassa(db, path: str | Path) -> dict:
    con = _open(path)
    try:
        if "workers" not in _tables(con) or "checks" not in _tables(con):
            raise ValueError("bu kassa bazasi emas")
        with db.tx():
            st = _kassa(db, con)
        db._cache.clear()
    finally:
        con.close()
    from .kassa import fill_missing_prices
    filled = fill_missing_prices(db)                      # faqat narxi yo'q cheklar (eski narxlar o'zgarmaydi)
    if filled:
        st["narx qo'yildi"] = filled
    db.set("kassa_imported", time.strftime("%Y-%m-%d %H:%M"))
    return st


def _kassa(db, con) -> dict:
    st: dict[str, int] = {}
    # qayta ko'chirishda eski kassa ma'lumotlari almashtiriladi (zaderjka/kech qolish jarimalari qoladi)
    db.run("DELETE FROM checks")
    db.run("DELETE FROM reports")
    db.run("DELETE FROM adj WHERE source NOT IN ('delay','late')")
    db.run("DELETE FROM transfers")
    db.run("DELETE FROM shares")
    users = _rows(con, "users")
    tg_of: dict[int, int] = {}
    for u in users:
        if _g(u, "worker_id") and _g(u, "role") != "owner":
            tg_of.setdefault(u["worker_id"], u["tg_id"])
    # xodimlar
    wmap: dict[int, int] = {}
    wcols = _cols(con, "workers")
    created = 0
    for w in _rows(con, "workers"):
        kind = _g(w, "kind", "") if "kind" in wcols else ""
        if not kind:
            kind = "self" if _g(w, "is_self", 0) else "worker"
        tg = tg_of.get(w["id"])
        p = (P.by_tg(db, tg) if tg else None) or P.by_name(db, w["name"]) or P.by_username(db, w["name"])
        if kind == "self":
            p = p or db.one("SELECT * FROM people WHERE kassa_kind='self' LIMIT 1")
        if p is None:
            pid = P.add_person(db, w["name"], "", tg, kind)
            created += 1
        else:
            pid = p["id"]
            fields = {"kassa_kind": kind}
            if p["name"].lower() == (p["username"] or "").lower():
                fields["name"] = w["name"]               # nazoratdan kelgan «bayzed» → kassadagi «Bayzed»
            if tg and not p["tg_id"]:
                fields["tg_id"] = tg
            P.update_person(db, pid, **fields)
        if not _g(w, "active", 1):
            P.update_person(db, pid, active=0)
        if kind in ("self", "partner"):
            P.update_person(db, pid, attend=0)
        wmap[w["id"]] = pid
    st["xodimlar"] = len(wmap)
    st["yangi xodim"] = created
    for pid in set(wmap.values()):
        db.run("DELETE FROM pct WHERE person_id=?", (pid,))
    for r in _rows(con, "pct"):
        if r["worker_id"] in wmap:
            db.run("INSERT OR REPLACE INTO pct(person_id, from_day, percent) VALUES(?,?,?)",
                   (wmap[r["worker_id"]], r["from_day"], r["percent"]))
    # narxlar
    pr = _rows(con, "prices")
    if pr:
        db.run("DELETE FROM prices")
        for r in pr:
            db.run("INSERT INTO prices(lo, hi, usd) VALUES(?,?,?)", (r["lo"], r["hi"], r["usd"]))
    st["narxlar"] = len(pr)
    # hisobotlar va cheklar
    rmap: dict[int, int] = {}
    for r in _rows(con, "reports"):
        cur = db.run("INSERT INTO reports(person_id, chat_id, msg_id, sender_id, sender_name, raw, status, created) "
                     "VALUES(?,?,?,?,?,?,?,?)",
                     (wmap.get(_g(r, "worker_id")), _g(r, "chat_id"), _g(r, "msg_id"), _g(r, "sender_id"),
                      _g(r, "sender_name", ""), _g(r, "raw", ""), _g(r, "status", "pending"), _g(r, "created", "")))
        rmap[r["id"]] = int(cur.lastrowid)
    st["hisobotlar"] = len(rmap)
    n = 0
    ccols = _cols(con, "checks")
    for c in _rows(con, "checks"):
        if c["report_id"] not in rmap:
            continue
        pay = wmap.get(_g(c, "pay")) if "pay" in ccols and _g(c, "pay") else None
        db.run("INSERT INTO checks(report_id, rd, amount, usd, skip, pay) VALUES(?,?,?,?,?,?)",
               (rmap[c["report_id"]], _g(c, "rd"), c["amount"], _g(c, "usd"), _g(c, "skip", 0), pay))
        n += 1
    st["cheklar"] = n
    # jarima / bonus / avans
    n = 0
    for a in _rows(con, "adj"):
        if a["worker_id"] not in wmap or _g(a, "kind") not in ("fine", "bonus", "adv"):
            continue
        db.run("INSERT INTO adj(person_id, kind, usd, day, source, note, chat_id, msg_id, cancelled, pending, created_ts) "
               "VALUES(?,?,?,?,'import',?,?,?,?,?,?)",
               (wmap[a["worker_id"]], a["kind"], a["usd"], a["day"], (_g(a, "raw", "") or "")[:200], _g(a, "chat_id"),
                _g(a, "msg_id"), _g(a, "cancelled", 0), _g(a, "pending", 0), int(time.time())))
        n += 1
    if not any(True for _ in _rows(con, "adj") if _g(_, "raw", "") == "аванс (старый)"):
        for a in _rows(con, "advances"):            # juda eski versiya: avanslar alohida jadvalda
            if a["worker_id"] in wmap:
                db.run("INSERT INTO adj(person_id, kind, usd, day, source, note, created_ts) "
                       "VALUES(?,'adv',?,?,'import',?,?)", (wmap[a["worker_id"]], a["usd"], a["day"],
                                                           _g(a, "note", "") or "аванс", int(time.time())))
                n += 1
    st["jarima/bonus/avans"] = n
    n = 0
    for t in _rows(con, "transfers"):
        if t["from_id"] in wmap and t["to_id"] in wmap:
            db.run("INSERT INTO transfers(day, from_id, to_id, pct, cancelled) VALUES(?,?,?,?,?)",
                   (t["day"], wmap[t["from_id"]], wmap[t["to_id"]], t["pct"], _g(t, "cancelled", 0)))
            n += 1
    st["o'tkazmalar"] = n
    n = 0
    for s in _rows(con, "shares"):
        if s["from_id"] in wmap and s["to_id"] in wmap:
            # egasining qarori: ulush xodim zp sidan emas — akkaunt kassasidan, egasining qismidan to'lanadi
            db.run("INSERT INTO shares(to_id, from_id, pct, base, mode, from_day, active) VALUES(?,?,?,'kassa','owner',?,?)",
                   (wmap[s["to_id"]], wmap[s["from_id"]], s["pct"], _g(s, "from_day", "2000-01-01"),
                    _g(s, "active", 1)))
            n += 1
    st["ulushlar"] = n
    # foydalanuvchilar: ega (ikkinchi akkaunt) va adminlar
    n = 0
    for u in users:
        role = _g(u, "role", "worker")
        if role in ("owner", "admin"):
            level = "owner" if role == "owner" else "full"
            cur = db.one("SELECT level FROM admins WHERE user_id=?", (u["tg_id"],))
            if cur is None or (level == "owner" and cur["level"] != "owner"):
                P.set_admin(db, u["tg_id"], level, _g(u, "name", "") or "")
                n += 1
    st["adminlar"] = n
    return st
