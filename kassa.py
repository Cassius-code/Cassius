"""Kassa: cheklar, prays, zp, jarima/bonus/avans, ulushlar, o'tkazmalar — hisob-kitob (Telegram'siz, sinaladi).

Eski kassa botining (logic.py) ishlagan qismlari saqlangan, egasi bilan kelishilgan o'zgarishlar:
* «Kim ishladi» (замена): kassa va cheklar AKKAUNT egasida qoladi, faqat zp ishlagan odamga o'tadi (o'z foizi bilan).
* Chek narxi ($) yozilgan paytda qotadi: prays keyin o'zgarsa ham o'tgan kunlar o'zgarmaydi.
* Har odamda «zp hisoblash» yoqgichi (zp_on). O'chiq: zp hisoblanmaydi, faqat kassa va jarima/bonus/avans.
* Ulush (share): akkaunt kassasidan X% (egasi to'laydi) yoki zp dan X% (ushlanadi).
* Jarima va bonus Arturning (hamkor) hisobiga: Artur = kassa × % + jarimalar − bonuslar.
"""
from __future__ import annotations

import contextvars
import datetime as dt
import re
import time
from collections import OrderedDict
from decimal import ROUND_HALF_UP, Decimal

from . import people as P
from .db import Database

PAYABLE = ("worker", "self")
SEED_PRICES = [
    (400, 700, 4), (750, 1150, 5), (1400, 1400, 7), (1650, 2250, 7),
    (2300, 2800, 10), (3300, 3700, 13), (4000, 4000, 17), (6000, 6000, 25),
    (7000, 7000, 30), (9000, 12200, 100), (19200, 19200, 200), (49200, 49200, 500),
]


# Kim o'zgartiryapti (panel/guruh handleri o'rnatadi) — tarix uchun
ACTOR: contextvars.ContextVar = contextvars.ContextVar("kassa_actor", default=None)


def r2(v) -> float:
    """Pul yaxlitlash: 0.915 -> 0.92 (float xatosisiz)."""
    return float(Decimal(repr(round(float(v), 8))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def iso(d) -> str:
    return d if isinstance(d, str) else d.isoformat()


def week_start(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def seed_prices(db: Database) -> None:
    if not db.one("SELECT 1 FROM prices"):
        db.many("INSERT INTO prices(lo, hi, usd) VALUES(?,?,?)", SEED_PRICES)


# ───────────────────────── foizlar
def percent_on(db: Database, pid: int, day) -> float:
    r = db.one("SELECT percent FROM pct WHERE person_id=? AND from_day<=? ORDER BY from_day DESC LIMIT 1",
               (pid, iso(day)))
    return float(r["percent"]) if r else 0.0


def set_percent(db: Database, pid: int, percent: float, from_day) -> None:
    old = percent_on(db, pid, from_day)
    if old != float(percent):
        log(db, "pct", pid, from_day, None, f"{old:g}", f"{float(percent):g}")
    db.run("INSERT OR REPLACE INTO pct(person_id, from_day, percent) VALUES(?,?,?)", (pid, iso(from_day), percent))


def owner_pct_on(db: Database, acct: int, day) -> float | None:
    """Sizning foizingiz shu akkaunt kassasidan (haftalik foizlar). None — eski usul (Artur o'z foizi, qolgani sizga)."""
    r = db.one("SELECT pct FROM owner_pct WHERE acct=? AND from_day<=? ORDER BY from_day DESC LIMIT 1",
               (acct, iso(day)))
    return float(r["pct"]) if r else None


def set_owner_pct(db: Database, acct: int, value: float, from_day) -> None:
    old = owner_pct_on(db, acct, from_day)
    if old != float(value):
        log(db, "opct", acct, from_day, None, "" if old is None else f"{old:g}", f"{float(value):g}")
    db.run("INSERT OR REPLACE INTO owner_pct(acct, from_day, pct) VALUES(?,?,?)", (acct, iso(from_day), float(value)))


def make_kassa_person(db: Database, pid: int, kind: str, percent: float, from_day="2000-01-01") -> None:
    P.update_person(db, pid, kassa_kind=kind)
    if not db.one("SELECT 1 FROM pct WHERE person_id=?", (pid,)):
        set_percent(db, pid, percent, from_day)


# ───────────────────────── prays (narx yozilgan paytda qotadi)
def price_for(db: Database, amount: int) -> float | None:
    r = db.one("SELECT usd FROM prices WHERE lo<=? AND hi>=? ORDER BY (hi-lo) ASC LIMIT 1", (amount, amount))
    return float(r["usd"]) if r else None


def prices(db: Database):
    return db.all("SELECT * FROM prices ORDER BY lo")


def fill_missing_prices(db: Database) -> int:
    """Narxi yo'q cheklarga (prays topilmagan edi) narx qo'yish. Narxi borlari O'ZGARMAYDI."""
    n = 0
    for c in db.all("SELECT id, amount FROM checks WHERE usd IS NULL"):
        p = price_for(db, c["amount"])
        if p is not None:
            db.run("UPDATE checks SET usd=? WHERE id=?", (p, c["id"]))
            n += 1
    return n


def price_text(lo, hi, usd) -> str:
    return (f"{lo}" if lo == hi else f"{lo}-{hi}") + f"={float(usd):g}"


def add_price(db: Database, lo: int, hi: int, usd: float) -> None:
    log(db, "price", None, None, None, "", price_text(lo, hi, usd))
    db.run("INSERT INTO prices(lo, hi, usd) VALUES(?,?,?)", (min(lo, hi), max(lo, hi), usd))
    fill_missing_prices(db)


def update_price(db: Database, pid: int, lo: int, hi: int, usd: float) -> None:
    o = db.one("SELECT * FROM prices WHERE id=?", (pid,))
    if o is not None:
        log(db, "price", None, None, pid, price_text(o["lo"], o["hi"], o["usd"]), price_text(lo, hi, usd))
    db.run("UPDATE prices SET lo=?, hi=?, usd=? WHERE id=?", (min(lo, hi), max(lo, hi), usd, pid))
    fill_missing_prices(db)


def del_price(db: Database, pid: int) -> None:
    o = db.one("SELECT * FROM prices WHERE id=?", (pid,))
    if o is not None:
        log(db, "price", None, None, pid, price_text(o["lo"], o["hi"], o["usd"]), "")
    db.run("DELETE FROM prices WHERE id=?", (pid,))


# ───────────────────────── matnni tushunish (faqat raqamli hisobot xabarlari)
RD_FIND = re.compile(r"(?<![A-Za-zА-Яа-яЁё])(?:rd|рд)\W{0,3}(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?", re.I)
RD_WORD = re.compile(r"(?<![A-Za-zА-Яа-яЁё])(?:rd|рд)(?![A-Za-zА-Яа-яЁё])", re.I)
DATE_RE = re.compile(r"(?<!\d)\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?(?!\d)")
DATE_G = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?(?!\d)")
TIME_RE = re.compile(r"\d{1,2}:\d{2}")
NUM_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d{3})+|\d{1,2}(?: \d{3})+|\d{3,6})(?!\d)")
TOTAL_RE = re.compile(r"итого|всего|jami|umumiy|total|касса|kassa|сумма|зп\b|зарплат|oylik|бонус|штраф|аванс|bonus|"
                      r"shtraf|avans", re.I)


def mk_date(d, m, y=None, ref: dt.date | None = None) -> dt.date | None:
    ref = ref or dt.date.today()
    try:
        if y:
            y = int(y)
            y = 2000 + y if y < 100 else y
            return dt.date(y, int(m), int(d))
        r = dt.date(ref.year, int(m), int(d))
        if r > ref + dt.timedelta(days=45):
            r = dt.date(ref.year - 1, int(m), int(d))
        return r
    except ValueError:
        return None


def find_rd(line: str, ref=None):
    m = RD_FIND.search(line)
    return mk_date(m.group(1), m.group(2), m.group(3), ref) if m else None


def parse_dates(text: str, ref=None) -> list[dt.date]:
    out = []
    for m in DATE_G.finditer(text):
        d = mk_date(m.group(1), m.group(2), m.group(3), ref)
        if d:
            out.append(d)
    return out


def has_rd(text: str) -> bool:
    return bool(RD_FIND.search(text))


def is_report_like(text: str) -> bool:
    """Xabar faqat raqam/sana/Rd/ajratgichdan iborat bo'lsa — hisobot. Boshqa gap o'qilmaydi."""
    t = RD_WORD.sub(" ", text.strip())
    return bool(t.strip()) and re.fullmatch(r"[\d\s,.;+=:/\-–—]+", t) is not None


def line_amounts(line: str) -> list[int]:
    if TOTAL_RE.search(line):
        return []
    body = line.rsplit("=", 1)[0] if "=" in line else line
    body = TIME_RE.sub(" ", DATE_RE.sub(" ", RD_FIND.sub(" ", body)))
    out = []
    for m in NUM_RE.finditer(body):
        v = int(re.sub(r"\D", "", m.group(1)))
        if 300 <= v <= 99999:
            out.append(v)
    return out


def parse_report(text: str, ref=None) -> list[tuple[dt.date, int]]:
    """Hisobot kuni = 'Rd dd.mm' (chekdan keyingi qatorda, shu qatorda yoki sarlavhada). Rd yo'q — ref (yozilgan kun)."""
    ref = ref or dt.date.today()
    ents = [(find_rd(line, ref), line_amounts(line)) for line in text.splitlines()]
    mode, seen = "suffix", False
    for rd, amts in ents:
        if rd and not amts:
            mode = "suffix" if seen else "header"
            break
        if amts:
            seen = True
    slots, pending, cur = [], [], None
    for rd, amts in ents:
        if rd and amts:
            slots += [[rd, a] for a in amts]
            cur = rd
        elif rd:
            if mode == "suffix":
                for i in pending:
                    slots[i][0] = rd
                pending = []
            cur = rd
        elif amts:
            for a in amts:
                if mode == "header" and cur:
                    slots.append([cur, a])
                else:
                    slots.append([None, a])
                    pending.append(len(slots) - 1)
    fill = cur or ref
    return [(rd or fill, a) for rd, a in slots]


def report_checks(text: str, post: dt.date, is_owner: bool) -> list[tuple[dt.date, int]]:
    out = parse_report(text, post)
    if is_owner and out and not has_rd(text):
        lines = [(line_amounts(ln), set(parse_dates(ln, post))) for ln in text.splitlines()]
        filled = [x for x in lines if x[0]]
        if filled and all(x[1] for x in filled):
            common = set.intersection(*[x[1] for x in filled])
            if len(common) == 1:
                d = next(iter(common))
                return [(d, a) for _, a in out]
    return out


def kassa_people(db: Database, active_only=True, kinds=("worker", "self", "pool")):
    return P.people(db, active_only=active_only, kinds=kinds)


def person_by_name_in(db: Database, text: str, kinds=("worker", "self", "pool")) -> int | None:
    for p in sorted(kassa_people(db, kinds=kinds), key=lambda p: -len(p["name"])):
        if re.search(r"(?<!\w)" + re.escape(p["name"]) + r"(?!\w)", text, re.I):
            return p["id"]
    return None


NAME_HEAD = re.compile(r"^@?([^\W\d_][\w'’ʻʼ`.\- ]{0,38}?)\s*[:.\-–—]?\s*(?=$|\d|(?:rd|рд)(?![^\W\d_]))(.*)$", re.I)


def split_tag(db: Database, text: str) -> tuple[int | None, str, str]:
    """Hisobot tepasida akkaunt nomi: «Lazarus\n1950 2600», «Baxa 19.10\n1950», «@baxa: rd 19.10\n1950».
    -> (person_id | None, hisobot qismi, nom). Nom tanilmasa person_id=None, lekin nom qaytadi (yangi xodim)."""
    lines = text.strip().splitlines()
    if not lines:
        return None, text, ""
    m = NAME_HEAD.match(lines[0].strip())
    if not m:
        return None, text, ""
    name = m.group(1).strip().rstrip(":.-–—").strip()
    low = name.lower().lstrip("@")
    if not name or low in ("rd", "рд") or TOTAL_RE.search(name) or KIND_RE.search(name):
        return None, text, ""
    rest = "\n".join(x for x in [m.group(2).strip()] + lines[1:] if x.strip())
    if not rest or not is_report_like(rest):
        return None, text, ""
    for p in kassa_people(db, active_only=False):
        if low in (p["name"].lower(), p["username"]):
            return p["id"], rest, p["name"]
    return None, rest, name[:40]


# ───────────────────────── jarima / bonus / avans matndan («@bayzed штраф 5», «штраф Bayzed 5$», «5 бонус @cred»)
KIND_PAT = (r"штраф\w*|shtraf\w*|jarima\w*|бонус\w*|bonus\w*|премия\w*|прем\w*|pryob\w*|priyob\w*|prem\w*"
            r"|аванс\w*|avans\w*|avanc\w*")
KIND_RE = re.compile(KIND_PAT, re.I)


def has_kind(text: str) -> bool:
    return bool(KIND_RE.search(text or ""))


def kind_of(tok: str) -> str:
    if re.match(r"штраф|shtraf|jarima", tok, re.I):
        return "fine"
    if re.match(r"аванс|avans|avanc", tok, re.I):
        return "adv"
    return "bonus"


def parse_adjustments(db: Database, text: str) -> list[dict]:
    """-> [{kind, person_id|None, usd}]. Tartib istalgancha: so'z, @user/ism, summa."""
    ps = P.people(db, kinds=("worker", "self", "partner"))
    names = sorted([p["name"] for p in ps], key=len, reverse=True)
    by_name = {p["name"].lower(): p["id"] for p in ps}
    by_user = {p["username"]: p["id"] for p in P.people(db) if p["username"]}
    name_pat = "|".join(re.escape(n) for n in names) or "(?!x)x"
    tok = re.compile(rf"(?P<kind>{KIND_PAT})|@(?P<user>[A-Za-z0-9_]{{3,32}})|(?P<name>(?<!\w)(?:{name_pat})(?!\w))"
                     rf"|(?P<num>\d+(?:[.,]\d+)?)", re.I)
    t2 = DATE_RE.sub(" ", text)
    kind = pid = None
    items, kinds, pids = [], set(), set()
    for m in tok.finditer(t2):
        if m.group("kind"):
            kind = kind_of(m.group("kind"))
            kinds.add(kind)
        elif m.group("user"):
            pid = by_user.get(m.group("user").lower())
            pids.add(pid)
        elif m.group("name"):
            pid = by_name.get(m.group("name").lower())
            pids.add(pid)
        else:
            v = float(m.group("num").replace(",", "."))
            if v > 0:
                items.append({"kind": kind, "person_id": pid, "usd": v})
    for it in items:
        if it["kind"] is None and len(kinds) == 1:
            it["kind"] = next(iter(kinds))
        if it["person_id"] is None and len(pids) == 1:
            it["person_id"] = next(iter(pids))
    return items


# ───────────────────────── tarix (o'zgartirishlar raqami ham, tarixi ham saqlanadi)
def log(db: Database, kind: str, person_id=None, day=None, ref_id=None, old="", new="") -> None:
    db.run("INSERT INTO audit(ts, actor, kind, person_id, day, ref_id, old, new) VALUES(?,?,?,?,?,?,?,?)",
           (int(time.time()), ACTOR.get(), kind, person_id, iso(day) if day else None, ref_id, str(old)[:200],
            str(new)[:200]))


def history(db: Database, day: str | None = None, person_id: int | None = None, limit: int = 25):
    where, args = [], []
    if day:
        where.append("day=?")
        args.append(day)
    if person_id:
        where.append("person_id=?")
        args.append(person_id)
    sql = "SELECT * FROM audit" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY id DESC LIMIT ?"
    return db.all(sql, (*args, limit))


def amounts_text(amounts) -> str:
    return " ".join(str(a) for a in amounts)


# ───────────────────────── boshlang'ich kassa va umumiy reyting
OPENING_SEED = [("Bayzed", 454559), ("Cred", 421380), ("Cashliy", 323803)]   # egasi bergan: 3 haftalik kassa
OPENING_SINCE = "2026-10-19"


def seed_opening(db: Database) -> None:
    if db.get("opening_seeded") == "1":
        return
    if not db.one("SELECT 1 FROM opening"):
        db.many("INSERT OR IGNORE INTO opening(name, raw) VALUES(?,?)", OPENING_SEED)
        if not db.get("opening_since"):
            db.set("opening_since", OPENING_SINCE)
    db.set("opening_seeded", "1")


def openings(db: Database):
    return db.all("SELECT * FROM opening ORDER BY raw DESC")


def opening_since(db: Database) -> str:
    return db.get("opening_since") or OPENING_SINCE


def parse_openings(text: str) -> list[tuple[str, int]]:
    """«Bayzed 454559», «🥇 🟢 Bayzed—454,559», «1. Cred: 421 380» -> [(nom, summa)]."""
    out = []
    for line in text.splitlines():
        m = re.match(r"^\W*(?:\d{1,2}[.)]\s*)?\W*?([^\W\d_][\w'’ʻʼ`. \-]*?)\s*[—–\-:=]*\s*(\d[\d\s.,]*)\s*$",
                     line.strip())
        if not m:
            continue
        name = m.group(1).strip().rstrip("—–-:=").strip()
        digits = re.sub(r"\D", "", m.group(2))
        if name and digits and len(digits) <= 10:
            out.append((name[:40], int(digits)))
    return out


def set_openings(db: Database, items: list[tuple[str, int]], since: str | None = None) -> None:
    old = {r["name"].lower(): r["raw"] for r in openings(db)}
    db.run("DELETE FROM opening")
    db.many("INSERT OR REPLACE INTO opening(name, raw) VALUES(?,?)", items)
    log(db, "opening", None, since or opening_since(db), None, " ".join(f"{k}={v}" for k, v in old.items()),
        " ".join(f"{n}={v}" for n, v in items))
    if since:
        db.set("opening_since", since)
    db.set("opening_seeded", "1")


def cumulative_rating(db: Database, today: dt.date) -> list[tuple[str, int, int | None]]:
    """Umumiy reyting: boshlang'ich kassa + shu sanadan beri cheklar yig'indisi. -> [(nom, jami, person_id)]."""
    since = opening_since(db)
    tot: dict[str, list] = {}
    for o in openings(db):
        tot[o["name"].lower()] = [o["name"], int(o["raw"]), None]
    for row in db.all("SELECT r.person_id pid, p.name name, p.kassa_kind kind, SUM(ch.amount) raw FROM checks ch "
                      "JOIN reports r ON r.id=ch.report_id JOIN people p ON p.id=r.person_id WHERE r.status='done' "
                      "AND ch.skip=0 AND ch.rd BETWEEN ? AND ? GROUP BY r.person_id", (since, iso(today))):
        if row["kind"] not in ("worker", "self", "pool"):
            continue
        k = row["name"].lower()
        if k in tot:
            tot[k][1] += int(row["raw"] or 0)
            tot[k][2] = row["pid"]
        else:
            tot[k] = [row["name"], int(row["raw"] or 0), row["pid"]]
    return sorted(((n, v, pid) for n, v, pid in tot.values() if v > 0), key=lambda x: -x[1])


# ───────────────────────── yopilgan kunlar («✅ Kunni yopish»)
def day_totals(db: Database, day: str) -> tuple[int, int, float]:
    row = db.one("SELECT COUNT(*) n, COALESCE(SUM(ch.amount),0) raw, COALESCE(SUM(ch.usd),0) usd FROM checks ch "
                 "JOIN reports r ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 AND ch.rd=?", (iso(day),))
    return int(row["n"]), int(row["raw"]), r2(row["usd"])


def day_totals_range(db: Database, start, end) -> tuple[int, int, float]:
    row = db.one("SELECT COUNT(*) n, COALESCE(SUM(ch.amount),0) raw, COALESCE(SUM(ch.usd),0) usd FROM checks ch "
                 "JOIN reports r ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ?",
                 (iso(start), iso(end)))
    return int(row["n"]), int(row["raw"]), r2(row["usd"])


def closed(db: Database, day) -> dict | None:
    row = db.one("SELECT * FROM closed_days WHERE day=?", (iso(day),))
    return dict(row) if row else None


def is_closed(db: Database, day) -> bool:
    return bool(day) and db.one("SELECT 1 FROM closed_days WHERE day=?", (iso(day),)) is not None


def close_day(db: Database, day) -> None:
    n, raw, usd = day_totals(db, iso(day))
    db.run("INSERT OR REPLACE INTO closed_days(day, ts, actor, n, raw, usd) VALUES(?,?,?,?,?,?)",
           (iso(day), int(time.time()), ACTOR.get(), n, raw, usd))
    log(db, "day_close", day=day, new=f"{n} {raw} {usd}")


def open_day(db: Database, day) -> None:
    db.run("DELETE FROM closed_days WHERE day=?", (iso(day),))
    log(db, "day_open", day=day)


def closed_days(db: Database, start, end) -> set[str]:
    return {r["day"] for r in db.all("SELECT day FROM closed_days WHERE day BETWEEN ? AND ?", (iso(start), iso(end)))}


# ───────────────────────── hisobot xabarlari (cheklar)
def report(db: Database, rid: int):
    return db.one("SELECT * FROM reports WHERE id=?", (rid,))


def amounts_of(db: Database, rid: int) -> list[int]:
    return [c["amount"] for c in db.all("SELECT amount FROM checks WHERE report_id=? ORDER BY id", (rid,))]


def report_amounts_by_msg(db: Database, chat_id: int, msg_id: int):
    r = db.one("SELECT id FROM reports WHERE chat_id=? AND msg_id=?", (chat_id, msg_id))
    return None if not r else amounts_of(db, r["id"])


def create_report(db: Database, person_id, chat_id, msg_id, sender_id, raw, checks, sender_name="") -> int:
    if msg_id is not None:
        for o in db.all("SELECT id, person_id, status FROM reports WHERE chat_id=? AND msg_id=?", (chat_id, msg_id)):
            if o["status"] == "done":                   # guruhda xabar tahrirlandi: eski raqamlar tarixda qoladi
                old = amounts_of(db, o["id"])
                days = report_days(db, o["id"])
                log(db, "rep_edit", o["person_id"] or person_id, days[0] if days else None, o["id"],
                    amounts_text(old), amounts_text(a for _d, a in checks))
            delete_report(db, o["id"])
    rid = int(db.run("INSERT INTO reports(person_id, chat_id, msg_id, sender_id, sender_name, raw, created) "
                     "VALUES(?,?,?,?,?,?,?)", (person_id, chat_id, msg_id, sender_id, sender_name, raw,
                                               dt.datetime.now().isoformat())).lastrowid)
    for rd, amt in checks:
        db.run("INSERT INTO checks(report_id, rd, amount, usd) VALUES(?,?,?,?)",
               (rid, iso(rd) if rd else None, amt, price_for(db, amt)))
    return rid


def delete_report(db: Database, rid: int) -> None:
    db.run("DELETE FROM checks WHERE report_id=?", (rid,))
    db.run("DELETE FROM reports WHERE id=?", (rid,))


def set_report_status(db: Database, rid: int, st: str) -> None:
    old = db.one("SELECT person_id, status FROM reports WHERE id=?", (rid,))
    db.run("UPDATE reports SET status=? WHERE id=?", (st, rid))
    if old is not None and old["status"] != st and "done" in (old["status"], st) and old["status"] != "pending":
        days = report_days(db, rid)
        log(db, "rep_" + st, old["person_id"], days[0] if days else None, rid, amounts_text(amounts_of(db, rid)))


def is_pool(db: Database, pid) -> bool:
    p = P.person(db, pid)
    return bool(p) and p["kassa_kind"] == "pool"


def report_needs(db: Database, rid: int):
    """Hisobotga nima yetishmaydi: ('person'|'date'|'price'|'op', arg) yoki None (tayyor)."""
    r = report(db, rid)
    if r is None:
        return None
    if r["person_id"] is None:
        return ("person", None)
    if db.one("SELECT 1 FROM checks WHERE report_id=? AND rd IS NULL", (rid,)):
        return ("date", None)
    row = db.one("SELECT amount FROM checks WHERE report_id=? AND usd IS NULL LIMIT 1", (rid,))
    if row:
        return ("price", row["amount"])
    if is_pool(db, r["person_id"]) and db.one("SELECT 1 FROM checks WHERE report_id=? AND pay IS NULL", (rid,)):
        return ("op", None)
    return None


def pending_reports(db: Database) -> list[int]:
    return [r["id"] for r in db.all("SELECT id FROM reports WHERE status='pending' ORDER BY id")]


def report_days(db: Database, rid: int) -> list[str]:
    return [r["rd"] for r in db.all("SELECT DISTINCT rd FROM checks WHERE report_id=? AND rd IS NOT NULL ORDER BY rd",
                                    (rid,))]


def supersede(db: Database, rid: int) -> list[dict]:
    """Yangi hisobot eskisini to'liq o'z ichiga olsa (>=2 chek) — eskisi hisobdan chiqadi."""
    r = report(db, rid)
    new = amounts_of(db, rid)
    out = []
    for d in report_days(db, rid):
        for o in db.all("SELECT DISTINCT r.id FROM reports r JOIN checks c ON c.report_id=r.id "
                        "WHERE r.person_id=? AND r.status='done' AND r.id<>? AND c.rd=?", (r["person_id"], rid, d)):
            old = amounts_of(db, o["id"])
            pool, ok = list(new), len(old) >= 2
            for a in old:
                if a in pool:
                    pool.remove(a)
                else:
                    ok = False
                    break
            if ok:
                set_report_status(db, o["id"], "replaced")
                out.append({"old": o["id"], "amounts": old, "kind": "replace"})
            elif len(old) == 1 and old == new:
                out.append({"old": o["id"], "amounts": old, "kind": "dup"})
    return out


def set_pay_report(db: Database, rid: int, pid) -> None:
    db.run("UPDATE checks SET pay=? WHERE report_id=? AND pay IS NULL", (pid, rid))


def set_pay_day(db: Database, acct: int, day: str, pid) -> None:
    """Shu akkauntning shu kundagi hamma cheklari uchun zp oluvchi (None = akkaunt egasi)."""
    log(db, "pay_day", acct, day, pid, "", pid or "")
    db.run("UPDATE checks SET pay=? WHERE rd=? AND report_id IN (SELECT id FROM reports WHERE person_id=? "
           "AND status='done')", (pid, day, acct))


def unassigned_days(db: Database, acct: int) -> list[str]:
    return [r["rd"] for r in db.all(
        "SELECT DISTINCT ch.rd FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE r.person_id=? "
        "AND r.status='done' AND ch.pay IS NULL AND ch.rd IS NOT NULL ORDER BY ch.rd", (acct,))]


def person_days(db: Database, pid: int, limit: int = 14):
    return db.all("SELECT ch.rd AS rd, COUNT(*) AS n FROM checks ch JOIN reports r ON r.id=ch.report_id "
                  "WHERE r.person_id=? AND r.status='done' AND ch.rd IS NOT NULL GROUP BY ch.rd ORDER BY ch.rd DESC "
                  "LIMIT ?", (pid, limit))


def day_checks(db: Database, pid: int, day: str):
    return db.all("SELECT ch.id, ch.amount, ch.usd, ch.skip, ch.pay FROM checks ch JOIN reports r ON r.id=ch.report_id "
                  "WHERE r.person_id=? AND r.status='done' AND ch.rd=? ORDER BY ch.id", (pid, day))


def check_row(db: Database, cid: int):
    return db.one("SELECT ch.*, r.person_id AS acct FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE ch.id=?",
                  (cid,))


def toggle_check(db: Database, cid: int) -> None:
    c = check_row(db, cid)
    db.run("UPDATE checks SET skip=1-skip WHERE id=?", (cid,))
    if c is not None:
        log(db, "chk_skip", c["acct"], c["rd"], cid, c["amount"], "on" if c["skip"] else "off")


def set_check_day(db: Database, cid: int, day: str) -> None:
    c = check_row(db, cid)
    db.run("UPDATE checks SET rd=? WHERE id=?", (day, cid))
    if c is not None and c["rd"] != day:
        log(db, "chk_day", c["acct"], day, cid, c["rd"] or "", c["amount"])


def add_check(db: Database, pid: int, day: str, amount: int) -> None:
    rid = db.run("INSERT INTO reports(person_id, chat_id, sender_name, raw, status, created) VALUES(?,?,?,?,?,?)",
                 (pid, 0, "вручную", str(amount), "done", dt.datetime.now().isoformat())).lastrowid
    cid = db.run("INSERT INTO checks(report_id, rd, amount, usd) VALUES(?,?,?,?)",
                 (rid, day, amount, price_for(db, amount))).lastrowid
    log(db, "chk_add", pid, day, cid, "", amount)


def edit_check_amount(db: Database, cid: int, amount: int) -> None:
    c = check_row(db, cid)
    db.run("UPDATE checks SET amount=?, usd=? WHERE id=?", (amount, price_for(db, amount), cid))
    if c is not None and c["amount"] != amount:
        log(db, "chk_amt", c["acct"], c["rd"], cid, c["amount"], amount)


def clear_day(db: Database, pid: int, day: str) -> int:
    ids = [r["id"] for r in db.all("SELECT DISTINCT r.id FROM reports r JOIN checks c ON c.report_id=r.id "
                                   "WHERE r.person_id=? AND c.rd=?", (pid, day))]
    old = [c["amount"] for c in day_checks(db, pid, day)]
    if old:
        log(db, "day_clear", pid, day, None, amounts_text(old), "")
    for i in ids:
        db.run("DELETE FROM checks WHERE report_id=? AND rd=?", (i, day))
        if not db.one("SELECT 1 FROM checks WHERE report_id=?", (i,)):
            db.run("DELETE FROM reports WHERE id=?", (i,))
    return len(ids)


# ───────────────────────── jarima / bonus / avans
def add_adj(db: Database, pid, kind, usd: float, day: str, source: str = "manual", note: str = "",
            chat_id=None, msg_id=None, ref_id=None, pending: int = 0) -> int:
    if not pending and kind:
        log(db, "adj_add", pid, day, None, source, f"{kind} {float(usd):g}")
    return int(db.run("INSERT INTO adj(person_id, kind, usd, day, source, note, chat_id, msg_id, ref_id, pending, "
                      "created_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                      (pid, kind, float(usd), iso(day), source, note[:300], chat_id, msg_id, ref_id, pending,
                       int(time.time()))).lastrowid)


def adj(db: Database, aid: int):
    return db.one("SELECT * FROM adj WHERE id=?", (aid,))


def adj_toggle(db: Database, aid: int) -> None:
    a = adj(db, aid)
    db.run("UPDATE adj SET cancelled=1-cancelled WHERE id=?", (aid,))
    if a is not None:
        log(db, "adj_on" if a["cancelled"] else "adj_off", a["person_id"], a["day"], aid, "", f"{a['kind']} {a['usd']:g}")


def drop_adj_msg(db: Database, chat_id: int, msg_id: int) -> None:
    db.run("DELETE FROM adj WHERE chat_id=? AND msg_id=?", (chat_id, msg_id))


def person_adjs(db: Database, pid: int, start: dt.date | None = None, end: dt.date | None = None, limit: int = 30):
    if start is None:
        return db.all("SELECT * FROM adj WHERE person_id=? AND pending=0 ORDER BY day DESC, id DESC LIMIT ?",
                      (pid, limit))
    return db.all("SELECT * FROM adj WHERE person_id=? AND pending=0 AND day BETWEEN ? AND ? ORDER BY day, id",
                  (pid, iso(start), iso(end)))


# ───────────────────────── o'tkazmalar va ulushlar
def add_transfer(db: Database, day: str, from_id: int, to_id: int, pct: float) -> int:
    log(db, "transfer", from_id, day, to_id, "", f"{pct:g}")
    return int(db.run("INSERT INTO transfers(day, from_id, to_id, pct) VALUES(?,?,?,?)",
                      (day, from_id, to_id, pct)).lastrowid)


def transfer_toggle(db: Database, tid: int) -> None:
    t = db.one("SELECT * FROM transfers WHERE id=?", (tid,))
    if t is not None:
        log(db, "transfer_on" if t["cancelled"] else "transfer_off", t["from_id"], t["day"], t["to_id"], "",
            f"{t['pct']:g}")
    db.run("UPDATE transfers SET cancelled=1-cancelled WHERE id=?", (tid,))


def person_transfers(db: Database, pid: int, limit: int = 10):
    return db.all("SELECT * FROM transfers WHERE from_id=? OR to_id=? ORDER BY id DESC LIMIT ?", (pid, pid, limit))


def shares(db: Database, pid: int | None = None, week: dt.date | None = None):
    """Shu haftada amal qiladigan ulushlar (week — dushanba; None — barchasi faol)."""
    sql, args = "SELECT * FROM shares WHERE active=1", []
    if week is not None:
        sql += " AND from_day<=? AND to_day>=?"
        args += [iso(week + dt.timedelta(days=6)), iso(week)]
    if pid is not None:
        sql += " AND (to_id=? OR from_id=?)"
        args += [pid, pid]
    return db.all(sql + " ORDER BY id", args)


def share(db: Database, sid: int):
    return db.one("SELECT * FROM shares WHERE id=?", (sid,))


def add_share(db: Database, to_id: int, from_id: int, pct: float, base: str = "kassa", mode: str = "owner",
              from_day: str = "2000-01-01") -> int:
    log(db, "share", to_id, from_day, from_id, "", f"{pct:g}")
    return int(db.run("INSERT INTO shares(to_id, from_id, pct, base, mode, from_day) VALUES(?,?,?,?,?,?)",
                      (to_id, from_id, pct, base, mode, iso(from_day))).lastrowid)


def share_change(db: Database, sid: int, week, **kw) -> int:
    """Ulushni shu haftadan boshlab o'zgartirish: o'tgan haftalar eski holida qoladi. -> amaldagi ulush id si."""
    sh = share(db, sid)
    if sh is None:
        return sid
    kw = {k: v for k, v in kw.items() if k in ("pct", "base", "mode") and v != sh[k]}
    if not kw:
        return sid
    if "pct" in kw:
        log(db, "share", sh["to_id"], week, sh["from_id"], f"{sh['pct']:g}", f"{float(kw['pct']):g}")
    if sh["from_day"] >= iso(week):
        for k, v in kw.items():
            db.run(f"UPDATE shares SET {k}=? WHERE id=?", (v, sid))
        return sid
    db.run("UPDATE shares SET to_day=? WHERE id=?", (iso(week - dt.timedelta(days=1)), sid))
    vals = {k: kw.get(k, sh[k]) for k in ("pct", "base", "mode")}
    return int(db.run("INSERT INTO shares(to_id, from_id, pct, base, mode, from_day, to_day) VALUES(?,?,?,?,?,?,?)",
                      (sh["to_id"], sh["from_id"], vals["pct"], vals["base"], vals["mode"], iso(week),
                       sh["to_day"])).lastrowid)


def update_share(db: Database, sid: int, **kw) -> None:
    """Hamma vaqt uchun (eski usul). Haftalik o'zgarish — share_change."""
    sh = share(db, sid)
    if sh is not None and "pct" in kw and float(kw["pct"]) != sh["pct"]:
        log(db, "share", sh["to_id"], None, sh["from_id"], f"{sh['pct']:g}", f"{float(kw['pct']):g}")
    for k, v in kw.items():
        if k in ("pct", "base", "mode", "from_day", "to_day", "to_id", "from_id"):
            db.run(f"UPDATE shares SET {k}=? WHERE id=?", (v, sid))


def end_share(db: Database, sid: int, week) -> None:
    """Shu haftadan boshlab ulush yo'q (o'tgan haftalarda qoladi)."""
    sh = share(db, sid)
    if sh is None:
        return
    log(db, "share", sh["to_id"], week, sh["from_id"], f"{sh['pct']:g}", "")
    if sh["from_day"] >= iso(week):
        db.run("UPDATE shares SET active=0 WHERE id=?", (sid,))
    else:
        db.run("UPDATE shares SET to_day=? WHERE id=?", (iso(week - dt.timedelta(days=1)), sid))


def del_share(db: Database, sid: int) -> None:
    sh = share(db, sid)
    if sh is not None:
        log(db, "share", sh["to_id"], None, sh["from_id"], f"{sh['pct']:g}", "")
    db.run("UPDATE shares SET active=0 WHERE id=?", (sid,))


# ───────────────────────── «🧮 Haftani hisoblash»: haftalik foizlar
ZP_MODES = ("button", "auto", "off")


def zp_mode(db: Database) -> str:
    m = db.get("zp_mode")
    return m if m in ZP_MODES else "button"


def week_confirmed(db: Database, week) -> bool:
    return db.one("SELECT 1 FROM weeks WHERE week=?", (iso(week_start(week)),)) is not None


def week_rules(db: Database, week: dt.date) -> dict:
    """Haftaning foizlar jadvali (dushanbadagi holat): akkauntlar, boshqa akkauntda ishlaganlar, ulushlar, nima yetishmaydi.

    -> {'accts': [...], 'subs': [...], 'shares': [...], 'missing': [(pid, kind)], 'over': [pid], 'confirmed': bool}
    """
    w0, w1 = iso(week), iso(week + dt.timedelta(days=6))
    ps = {p["id"]: p for p in db.all("SELECT * FROM people")}
    order = {p["id"]: i for i, p in enumerate(P.people(db, active_only=False))}
    accts = db.all("SELECT r.person_id acct, COUNT(*) n, COALESCE(SUM(ch.usd),0) usd, COALESCE(SUM(ch.amount),0) raw "
                   "FROM checks ch "
                   "JOIN reports r ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ? "
                   "AND r.person_id IS NOT NULL GROUP BY r.person_id", (w0, w1))
    payees = {row["pay"] for row in db.all(
        "SELECT DISTINCT ch.pay pay FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE r.status='done' "
        "AND ch.skip=0 AND ch.rd BETWEEN ? AND ? AND ch.pay IS NOT NULL", (w0, w1))}
    items, subs, missing, over = [], [], [], []
    kassa_sh: dict = {}                      # (acct, payer) -> % kassadan (siz yoki Artur to'laydi)
    sh_rows = shares(db, week=week)
    for sh in sh_rows:
        if sh["base"] == "kassa" and sh["mode"] in ("owner", "partner"):
            k = (sh["from_id"], sh["mode"])
            kassa_sh[k] = kassa_sh.get(k, 0.0) + sh["pct"]
    for a in sorted(accts, key=lambda x: order.get(x["acct"], 10 ** 6)):
        p = ps.get(a["acct"])
        if p is None or not p["kassa_kind"]:
            continue
        kind = p["kassa_kind"]
        wp = percent_on(db, p["id"], week) if kind in ("worker", "self") else None
        op = owner_pct_on(db, p["id"], week)
        if kind == "self" and op is None:
            op = 0.0
        it = {"pid": p["id"], "name": p["name"], "kind": kind, "n": a["n"], "usd": r2(a["usd"]), "raw": int(a["raw"]),
              "wpct": wp,
              "opct": op, "kshare": kassa_sh.get((p["id"], "partner"), 0.0),
              "kshare_owner": kassa_sh.get((p["id"], "owner"), 0.0), "zp_on": bool(p["zp_on"])}
        items.append(it)
        if kind == "worker" and p["zp_on"] and not wp:
            missing.append((p["id"], "acct"))
        elif kind in ("worker", "pool") and op is None:
            missing.append((p["id"], "acct"))
        elif kind == "self" and not wp:
            missing.append((p["id"], "acct"))
        total = (wp or 0) + (op or 0) + it["kshare"]
        if kind != "pool" and total > 100:
            over.append(p["id"])
    acct_ids = {it["pid"] for it in items}
    for pid in sorted(payees - acct_ids, key=lambda x: order.get(x, 10 ** 6)):
        p = ps.get(pid)
        if p is None or p["kassa_kind"] not in ("worker", "self"):
            continue
        wp = percent_on(db, pid, week)
        subs.append({"pid": pid, "name": p["name"], "kind": "sub", "wpct": wp, "zp_on": bool(p["zp_on"])})
        if p["zp_on"] and not wp:
            missing.append((pid, "sub"))
    return {"week": week, "accts": items, "subs": subs, "shares": sh_rows, "missing": missing, "over": over,
            "confirmed": week_confirmed(db, week)}


def confirm_week(db: Database, week: dt.date) -> None:
    """Haftani tasdiqlash: foizlar shu dushanbaga yozib qo'yiladi (keyin oldingi haftani tuzatsangiz ham bu hafta
    o'zgarmaydi), keyingi hafta shundan nusxa oladi."""
    w = week_rules(db, week)
    with_rows = [(it["pid"], it["kind"], it["wpct"], it["opct"]) for it in w["accts"]] + \
        [(it["pid"], "sub", it["wpct"], None) for it in w["subs"]]
    for pid, kind, wp, op in with_rows:
        if kind in ("worker", "self", "sub") and wp is not None:
            db.run("INSERT OR REPLACE INTO pct(person_id, from_day, percent) VALUES(?,?,?)", (pid, iso(week), wp))
        if kind in ("worker", "self", "pool") and op is not None:
            db.run("INSERT OR REPLACE INTO owner_pct(acct, from_day, pct) VALUES(?,?,?)", (pid, iso(week), op))
    db.run("INSERT OR REPLACE INTO weeks(week, ts, actor) VALUES(?,?,?)", (iso(week), int(time.time()), ACTOR.get()))
    log(db, "week_ok", None, week)


def unconfirm_week(db: Database, week: dt.date) -> None:
    db.run("DELETE FROM weeks WHERE week=?", (iso(week),))
    log(db, "week_open", None, week)


def zp_state(db: Database, start: dt.date, end: dt.date, today: dt.date) -> dict:
    """Zp ko'rsatish mumkinmi: auto — doim; off — hech qachon; button — davrdagi har hafta tasdiqlangan bo'lsa.
    -> {'ready': bool, 'mode': str, 'weeks': [dushanba, ...] (tasdiqlanmagan, chek bor)}"""
    mode = zp_mode(db)
    if mode == "auto":
        return {"ready": True, "mode": mode, "weeks": []}
    if mode == "off":
        return {"ready": False, "mode": mode, "weeks": []}
    weeks = []
    w = week_start(start)
    last = min(end, today)
    while w <= last:
        a, z = max(w, start), min(w + dt.timedelta(days=6), end)
        has = db.one("SELECT 1 FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE r.status='done' "
                     "AND ch.skip=0 AND ch.rd BETWEEN ? AND ? LIMIT 1", (iso(a), iso(z)))
        if has and (not week_confirmed(db, w) or week_rules(db, w)["missing"]):
            weeks.append(w)
        w += dt.timedelta(days=7)
    return {"ready": not weeks, "mode": mode, "weeks": weeks}


# ───────────────────────── «oylik berildi» davrlari
def last_payout(db: Database, pid: int):
    return db.one("SELECT * FROM payouts WHERE person_id=? ORDER BY upto_day DESC, id DESC LIMIT 1", (pid,))


def open_period(db: Database, pid: int, today: dt.date) -> tuple[dt.date, dt.date]:
    """Joriy hisob davri: oxirgi «oylik berildi»dan keyingi kundan bugungacha (yo'q bo'lsa — shu hafta dushanbasidan)."""
    lp = last_payout(db, pid)
    if lp is not None:
        start = dt.date.fromisoformat(lp["upto_day"]) + dt.timedelta(days=1)
        return min(start, today), today
    return week_start(today), today


def mark_paid(db: Database, pid: int, upto: dt.date, total: float | None, note: str = "") -> int:
    log(db, "paid", pid, upto, None, "", "" if total is None else f"{total:g}")
    return int(db.run("INSERT INTO payouts(person_id, upto_day, ts, total, note) VALUES(?,?,?,?,?)",
                      (pid, iso(upto), int(time.time()), total, note)).lastrowid)


def undo_paid(db: Database, payout_id: int) -> None:
    po = db.one("SELECT * FROM payouts WHERE id=?", (payout_id,))
    if po is not None:
        log(db, "paid_undo", po["person_id"], po["upto_day"], payout_id, "" if po["total"] is None else
            f"{po['total']:g}", "")
    db.run("DELETE FROM payouts WHERE id=?", (payout_id,))


def week_payout(db: Database, pid: int, week_end) -> dict | None:
    """Shu hafta (yakshanbagacha) to'langanmi: upto_day >= yakshanba bo'lgan eng yaqin to'lov."""
    row = db.one("SELECT * FROM payouts WHERE person_id=? AND upto_day>=? ORDER BY upto_day, id LIMIT 1",
                 (pid, iso(week_end)))
    return dict(row) if row else None


# ───────────────────────── solishtirish (o'tgan davrning xuddi shu kunlari bilan)
def compare_ranges(s: dt.date, e: dt.date, today: dt.date):
    """-> ((s, ce), (ps, pe)) yoki None. Davr hali tugamagan bo'lsa — faqat o'tgan kunlar solishtiriladi."""
    ce = min(e, today)
    if ce < s:
        return None
    span = (ce - s).days
    month_end = (e + dt.timedelta(days=1)).day == 1
    if s.day == 1 and month_end and e.month == s.month:
        ps = (s - dt.timedelta(days=1)).replace(day=1)
        pe = min(ps + dt.timedelta(days=span), s - dt.timedelta(days=1))
    else:
        length = (e - s).days + 1
        ps = s - dt.timedelta(days=length)
        pe = ps + dt.timedelta(days=span)
    return (s, ce), (ps, pe)


def delta_pct(cur: float, prev: float) -> float | None:
    if not prev or prev <= 0:
        return None
    return round((cur - prev) / prev * 100)


def compare(db: Database, s: dt.date, e: dt.date, today: dt.date) -> dict | None:
    """Akkauntlar bo'yicha kassa (cheklar yig'indisi): {'cur': {pid: raw}, 'prev': {pid: raw}, 'K', 'PK', ...}."""
    rr = compare_ranges(s, e, today)
    if rr is None:
        return None
    (cs, ce), (ps, pe) = rr
    def per(a, b):
        out: dict[int, float] = {}
        for row in db.all("SELECT r.person_id acct, SUM(ch.amount) raw FROM checks ch JOIN reports r ON r.id=ch.report_id "
                          "WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ? GROUP BY r.person_id",
                          (iso(a), iso(b))):
            out[row["acct"]] = float(row["raw"] or 0)
        return out
    cur, prev = per(cs, ce), per(ps, pe)
    return {"cur": cur, "prev": prev, "K": r2(sum(cur.values())), "PK": r2(sum(prev.values())), "ps": ps, "pe": pe,
            "partial": ce < e}


# ───────────────────────── oy yakuni
def month_bounds(year: int, month: int) -> tuple[dt.date, dt.date]:
    first = dt.date(year, month, 1)
    return first, (first + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)


def month_data(db: Database, year: int, month: int, today: dt.date) -> dict:
    first, last = month_bounds(year, month)
    end = min(last, today)
    b = calc(db, first, last)
    weeks = []
    ws = week_start(first)
    while ws <= last:
        a, z = max(ws, first), min(ws + dt.timedelta(days=6), last)
        n, raw, usd = 0, 0, 0.0
        for row in db.all("SELECT COUNT(*) n, COALESCE(SUM(ch.amount),0) raw, COALESCE(SUM(ch.usd),0) usd FROM checks ch "
                          "JOIN reports r ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? "
                          "AND ?", (iso(a), iso(z))):
            n, raw, usd = row["n"], row["raw"], r2(row["usd"])
        if a <= today:
            weeks.append({"s": a, "e": z, "n": n, "raw": raw, "usd": usd})
        ws += dt.timedelta(days=7)
    best = db.one("SELECT ch.rd d, SUM(ch.amount) usd FROM checks ch JOIN reports r ON r.id=ch.report_id "
                  "WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ? GROUP BY ch.rd ORDER BY usd DESC LIMIT 1",
                  (iso(first), iso(last)))
    days_n = db.scalar("SELECT COUNT(DISTINCT ch.rd) FROM checks ch JOIN reports r ON r.id=ch.report_id "
                       "WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ?", (iso(first), iso(last)))
    return {"first": first, "last": last, "end": end, "b": b, "weeks": weeks, "cmp": compare(db, first, last, today),
            "best": (best["d"], int(best["usd"] or 0)) if best and best["d"] else None, "days": days_n}


# ───────────────────────── HISOB-KITOB
def _row(p) -> dict:
    return {"p": p, "kind": p["kassa_kind"], "zp_on": bool(p["zp_on"]),
            # akkaunt sifatida (kassa shu odamniki)
            "n": 0, "raw": 0, "usd": 0.0, "days": OrderedDict(), "noprice": 0, "unassigned": 0,
            "paid_out": OrderedDict(),       # akkaunt cheklaridan boshqalarga o'tgan zp: {payee: usd}
            # zp oluvchi sifatida
            "earn": OrderedDict(),           # {(acct, pct): usd}
            "zp": 0.0,
            "fines": [], "bonuses": [], "advs": [], "fine": 0.0, "bonus": 0.0, "adv": 0.0,
            "outs": [], "ins": [], "tr_out": 0.0, "tr_in": 0.0,
            "sin": [], "sout": [], "sin_sum": 0.0, "sout_sum": 0.0,
            "total": None, "share_part": 0.0, "pf": 0.0, "pb": 0.0}


def calc(db: Database, start: dt.date, end: dt.date) -> dict:
    """Davr bo'yicha hamma narsa. -> {'rows': {pid: row}, 'order': [...], 'K', 'raw', 'n', 'owner': {...}}

    Har akkaunt kassasi (kun bo'yicha) shunday bo'linadi:
    * haftalik foizlar kiritilgan (owner_pct bor): ishlagan xodim % + siz % → qolgani Arturga;
    * eski usul (owner_pct yo'q): Artur — o'z foizi (50%), qolgani sizga (xodimlar zp si sizdan).
    Ulushlar: kassadan yoki zp dan; kim to'laydi — siz (owner), Artur (partner) yoki zp dan ushlanadi (deduct).
    """
    s, e = iso(start), iso(end)
    ps = {p["id"]: p for p in db.all("SELECT * FROM people")}
    rows = {pid: _row(p) for pid, p in ps.items() if p["kassa_kind"]}
    partner = next((p for p in ps.values() if p["kassa_kind"] == "partner" and p["active"]), None)
    pct_cache: dict = {}
    op_cache: dict = {}

    def pct(pid, day):
        k = (pid, day)
        if k not in pct_cache:
            pct_cache[k] = percent_on(db, pid, day)
        return pct_cache[k]

    def opct(acct, day):
        k = (acct, day)
        if k not in op_cache:
            op_cache[k] = owner_pct_on(db, acct, day)
        return op_cache[k]

    checks = db.all("SELECT ch.id cid, ch.rd, ch.amount, ch.usd, ch.skip, ch.pay, r.person_id acct "
                    "FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE r.status='done' AND ch.rd BETWEEN ? AND ? "
                    "ORDER BY ch.rd, ch.id", (s, e))
    base_zp: dict = {}               # (pid, day) -> zp (o'tkazma va zp-ulush uchun)
    acct_usd_day: dict = {}          # (acct, day) -> usd
    zp_ad: dict = {}                 # (acct, day) -> {"all", "on", "self", "off"} — shu akkaunt cheklaridan zp
    RAW = N = 0
    for c in checks:
        if c["skip"] or c["acct"] not in rows:
            continue
        a = rows[c["acct"]]
        usd = float(c["usd"]) if c["usd"] is not None else 0.0
        d = c["rd"]
        a["n"] += 1
        a["raw"] += c["amount"]
        a["usd"] += usd
        if c["usd"] is None:
            a["noprice"] += 1
        day = a["days"].setdefault(d, {"n": 0, "raw": 0, "usd": 0.0, "items": [], "ops": []})
        day["n"] += 1
        day["raw"] += c["amount"]
        day["usd"] += usd
        day["items"].append((c["amount"], usd))
        acct_usd_day[(c["acct"], d)] = acct_usd_day.get((c["acct"], d), 0.0) + usd
        RAW += c["amount"]
        N += 1
        payee = c["pay"] or (None if a["kind"] == "pool" else c["acct"])
        if payee is None or payee not in rows:
            a["unassigned"] += 1
            continue
        pr = rows[payee]
        pp = pct(payee, d)
        key = (c["acct"], pp)
        pr["earn"][key] = pr["earn"].get(key, 0.0) + usd
        z = usd * pp / 100
        base_zp[(payee, d)] = base_zp.get((payee, d), 0.0) + z
        bucket = zp_ad.setdefault((c["acct"], d), {"all": 0.0, "on": 0.0, "self": 0.0, "off": 0.0})
        bucket["all"] += z
        if pr["kind"] == "self":
            bucket["self"] += z
        elif pr["zp_on"]:
            bucket["on"] += z
        else:
            bucket["off"] += z
        if payee != c["acct"]:
            a["paid_out"][payee] = a["paid_out"].get(payee, 0.0) + usd
            name = ps[payee]["name"]
            if name not in day["ops"]:
                day["ops"].append(name)

    for pid, r in rows.items():
        if r["kind"] in PAYABLE:
            r["zp"] = r2(sum(u * p / 100 for (_acct, p), u in r["earn"].items()))

    # jarima / bonus / avans
    for a in db.all("SELECT * FROM adj WHERE cancelled=0 AND pending=0 AND day BETWEEN ? AND ? ORDER BY day, id",
                    (s, e)):
        r = rows.get(a["person_id"])
        if r is None:
            continue
        key = {"fine": "fines", "bonus": "bonuses", "adv": "advs"}.get(a["kind"])
        if key:
            r[key].append({"usd": float(a["usd"]), "day": a["day"], "source": a["source"], "note": a["note"],
                           "id": a["id"]})
    for r in rows.values():
        r["fine"] = r2(sum(x["usd"] for x in r["fines"]))
        r["bonus"] = r2(sum(x["usd"] for x in r["bonuses"]))
        r["adv"] = r2(sum(x["usd"] for x in r["advs"]))

    # ulushlar (sana oralig'i bilan): kassadan yoki zp dan; to'lovchi — siz / Artur / ushlanadi
    share_ad: dict = {}              # (acct, day) -> {"owner": x, "partner": y}
    for sh in db.all("SELECT * FROM shares WHERE active=1 AND from_day<=? AND to_day>=? ORDER BY id", (e, s)):
        if sh["from_id"] not in rows or sh["to_id"] not in rows:
            continue
        per_day: dict = {}
        if sh["base"] == "kassa":
            for (acct, d), u in acct_usd_day.items():
                if acct == sh["from_id"] and sh["from_day"] <= d <= sh["to_day"]:
                    per_day[d] = per_day.get(d, 0.0) + u * sh["pct"] / 100
        else:
            for (pid, d), z in base_zp.items():
                if pid == sh["from_id"] and sh["from_day"] <= d <= sh["to_day"]:
                    per_day[d] = per_day.get(d, 0.0) + z * sh["pct"] / 100
        amt = r2(sum(per_day.values()))
        if amt == 0:
            continue
        item = {"id": sh["id"], "amount": amt, "pct": sh["pct"], "base": sh["base"], "mode": sh["mode"]}
        rows[sh["to_id"]]["sin"].append({**item, "other": sh["from_id"]})
        if sh["mode"] == "deduct":
            rows[sh["from_id"]]["sout"].append({**item, "other": sh["to_id"]})
        else:
            payer = "partner" if sh["mode"] == "partner" else "owner"
            for d, v in per_day.items():
                share_ad.setdefault((sh["from_id"], d), {"owner": 0.0, "partner": 0.0})[payer] += v
    for r in rows.values():
        r["sin_sum"] = r2(sum(i["amount"] for i in r["sin"]))
        r["sout_sum"] = r2(sum(i["amount"] for i in r["sout"]))

    # akkaunt × kun: Artur va sizning qismingiz
    acct_split: dict = {}            # acct -> {"usd","artur","zp","share","pshare","mine"}
    artur_day: dict = {}
    modes = set()
    zero = {"all": 0.0, "on": 0.0, "self": 0.0, "off": 0.0}
    for (acct, d) in set(acct_usd_day) | set(share_ad):
        u = acct_usd_day.get((acct, d), 0.0)
        z = zp_ad.get((acct, d), zero)
        sh = share_ad.get((acct, d), {"owner": 0.0, "partner": 0.0})
        op = opct(acct, d)
        if partner is None:
            art = 0.0
        elif op is None:
            art = u * pct(partner["id"], d) / 100
            if u:
                modes.add("legacy")
        else:
            art = u - z["all"] - u * op / 100
            if u:
                modes.add("split")
        art_net = art - sh["partner"]
        mine = u - art - z["on"] - sh["owner"]
        x = acct_split.setdefault(acct, {"usd": 0.0, "artur": 0.0, "zp": 0.0, "share": 0.0, "pshare": 0.0,
                                         "mine": 0.0})
        x["usd"] += u
        x["artur"] += art_net
        x["zp"] += z["on"]
        x["share"] += sh["owner"]
        x["pshare"] += sh["partner"]
        x["mine"] += mine
        artur_day[d] = artur_day.get(d, 0.0) + art_net

    if partner is not None:
        rows[partner["id"]]["share_part"] = r2(sum(artur_day.values()))

    # o'tkazmalar: shu kundagi zp ning foizi (Artur uchun — shu kundagi qismi)
    for t in db.all("SELECT * FROM transfers WHERE cancelled=0 AND day BETWEEN ? AND ? ORDER BY day, id", (s, e)):
        if t["from_id"] not in rows or t["to_id"] not in rows:
            continue
        base = base_zp.get((t["from_id"], t["day"]), 0.0)
        if rows[t["from_id"]]["kind"] == "partner":
            base = artur_day.get(t["day"], 0.0)
        amt = r2(base * t["pct"] / 100)
        rows[t["from_id"]]["outs"].append({"id": t["id"], "day": t["day"], "other": t["to_id"], "amount": amt,
                                           "pct": t["pct"]})
        rows[t["to_id"]]["ins"].append({"id": t["id"], "day": t["day"], "other": t["from_id"], "amount": amt,
                                        "pct": t["pct"]})
    for r in rows.values():
        r["tr_out"] = r2(sum(o["amount"] for o in r["outs"]))
        r["tr_in"] = r2(sum(i["amount"] for i in r["ins"]))

    # jami
    payable = [r for r in rows.values() if r["kind"] in PAYABLE]
    pf = r2(sum(r["fine"] for r in payable))
    pb = r2(sum(r["bonus"] for r in payable))
    for r in rows.values():
        if r["kind"] in PAYABLE and r["zp_on"]:
            r["total"] = r2(r["zp"] - r["fine"] + r["bonus"] - r["adv"] - r["tr_out"] + r["tr_in"]
                            + r["sin_sum"] - r["sout_sum"])
        elif r["kind"] == "partner":
            r["pf"], r["pb"] = pf, pb
            r["total"] = r2(r["share_part"] + pf - pb - r["fine"] + r["bonus"] - r["adv"] - r["tr_out"] + r["tr_in"])

    K = r2(sum(acct_usd_day.values()))
    me = next((r for r in rows.values() if r["kind"] == "self"), None)
    per_acct = []
    for pid in [p for p in rows if p in acct_split]:
        x = acct_split[pid]
        per_acct.append({"pid": pid, "usd": r2(x["usd"]), "artur": r2(x["artur"]), "half": r2(x["usd"] - x["artur"]
                                                                                              - x["pshare"]),
                         "zp": r2(x["zp"]), "share": r2(x["share"]), "pshare": r2(x["pshare"]), "mine": r2(x["mine"]),
                         "self": rows[pid]["kind"] == "self"})
    unknown = [r["p"]["name"] for r in rows.values() if r["kind"] == "worker" and not r["zp_on"] and r["earn"]]
    zps = r2(sum(r["zp"] for r in rows.values() if r["kind"] == "worker" and r["zp_on"]))
    owner_paid = r2(sum(x["share"] for x in acct_split.values()))
    partner_paid = r2(sum(x["pshare"] for x in acct_split.values()))
    share_part = rows[partner["id"]]["share_part"] if partner else 0.0
    out_self = me["tr_out"] if me else 0.0
    in_self = me["tr_in"] if me else 0.0
    mine = r2(sum(x["mine"] for x in acct_split.values()))
    income = r2(mine - out_self + in_self)
    mode = "split" if modes == {"split"} else ("legacy" if modes <= {"legacy"} else "mixed")
    owner = {"K": K, "partner_pct": partner_pct_of(db, partner, e) if mode == "legacy" else None, "mode": mode,
             "half": r2(K - share_part - partner_paid), "zps": zps, "owner_paid": owner_paid,
             "partner_paid": partner_paid, "out_self": r2(out_self), "in_self": r2(in_self), "income": income,
             "mine": mine, "self_zp": me["zp"] if me else 0.0, "per_acct": per_acct, "unknown_zp": unknown,
             "partner_id": partner["id"] if partner else None,
             "partner_total": rows[partner["id"]]["total"] if partner else 0.0,
             "partner_share": share_part, "pf": pf, "pb": pb}
    order = [p["id"] for p in P.people(db, active_only=False) if p["kassa_kind"]]
    return {"rows": rows, "order": order, "K": K, "raw": RAW, "n": N, "owner": owner, "names":
            {pid: p["name"] for pid, p in ps.items()}}


def partner_pct_of(db: Database, partner, day) -> float:
    return percent_on(db, partner["id"], day) if partner else 50.0


def has_data(r: dict) -> bool:
    if r["kind"] == "partner":
        return r["share_part"] > 0 or bool(r["fines"] or r["bonuses"] or r["advs"] or r["outs"] or r["ins"])
    return bool(r["n"] or r["earn"] or r["fines"] or r["bonuses"] or r["advs"] or r["outs"] or r["ins"]
                or r["sin"] or r["sout"])


def day_zp(db: Database, pid: int, day: str) -> float:
    d = dt.date.fromisoformat(day)
    r = calc(db, d, d)["rows"].get(pid)
    if r is None:
        return 0.0
    if r["kind"] == "partner":
        return r["share_part"]
    return r["zp"]


def period_range(key: str, today: dt.date) -> tuple[dt.date, dt.date]:
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", key):
        d = dt.date.fromisoformat(key)
        return d, d
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}_\d{4}-\d{2}-\d{2}", key):
        a, b = key.split("_")
        return dt.date.fromisoformat(a), dt.date.fromisoformat(b)
    if key == "yd":
        y = today - dt.timedelta(days=1)
        return y, y
    if key == "tw":
        return week_start(today), week_start(today) + dt.timedelta(days=6)
    if key == "lw":
        mon = week_start(today) - dt.timedelta(days=7)
        return mon, mon + dt.timedelta(days=6)
    if key == "tm":
        first = today.replace(day=1)
        return first, (first + dt.timedelta(days=32)).replace(day=1) - dt.timedelta(days=1)
    if key == "lm":
        last = today.replace(day=1) - dt.timedelta(days=1)
        return last.replace(day=1), last
    return today, today
