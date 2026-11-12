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
# Kimdir o'rniga butun kun boshqasi ishlasa («🔁 Kim ishladi»), o'sha kunga yozilgan jarima/bonus — ishlagan odamga
# (egasi, 2026-11-02). Kech qolish jarimasi va avans — shaxsiy, o'tmaydi.
MOVABLE = ("manual", "group", "delay", "remind")
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
# «Rd 04.11», shuningdek RD raqami bilan: «Rd3 04.11», «Rd 3 04.11», «Rd3.1 04.11» (🔗 /gaz achoti, egasi 2026-11-04)
RD_FIND = re.compile(r"(?<![A-Za-zА-Яа-яЁё])(?:rd|рд)\W{0,3}(?:(?P<no>\d{1,2})(?:\.\d)?[ \t]+)?"
                     r"(?P<d>\d{1,2})[./-](?P<m>\d{1,2})(?:[./-](?P<y>\d{2,4}))?", re.I)
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
    return mk_date(m.group("d"), m.group("m"), m.group("y"), ref) if m else None


def find_rd_no(line: str) -> str | None:
    """«Rd3 04.11» → «3» (RD raqami; «Rd3.1» ham «3»), «Rd 04.11» → None."""
    m = RD_FIND.search(line)
    return m.group("no") if m and m.group("no") else None


def parse_dates(text: str, ref=None) -> list[dt.date]:
    out = []
    for m in DATE_G.finditer(text):
        d = mk_date(m.group(1), m.group(2), m.group(3), ref)
        if d:
            out.append(d)
    return out


def has_rd(text: str) -> bool:
    return bool(RD_FIND.search(text))


PHONE_RE = re.compile(r"\+\s*\d[\d\s\-()]{7,}")
PHONE_LOCAL = re.compile(r"(998[\s\-]?)?\(?\d{2}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")   # 90 123 45 67


def is_phone(text: str) -> bool:
    """Telefon raqami — chek emas: «+1 470 514 4558», «+998 90 123 45 67», «998901234567», «90 123 45 67».
    Kassa summalari 3–6 xonali bo'ladi, shuning uchun 9+ xonali bitta raqam ham telefon."""
    for line in text.strip().splitlines():
        s = line.strip()
        digits = len(re.sub(r"\D", "", s))
        if PHONE_RE.fullmatch(s) and 10 <= digits <= 15:
            return True
        if re.fullmatch(r"\d{9,15}", s):
            return True
        if PHONE_LOCAL.fullmatch(s) and digits in (9, 12):
            return True
    return False


def is_report_like(text: str) -> bool:
    """Xabar faqat raqam/sana/Rd/ajratgichdan iborat bo'lsa — hisobot. Boshqa gap o'qilmaydi. Telefon raqami — yo'q."""
    t = RD_WORD.sub(" ", text.strip())
    return bool(t.strip()) and re.fullmatch(r"[\d\s,.;+=:/\-–—]+", t) is not None and not is_phone(text)


def looks_like_report(db: Database, text: str) -> bool:
    """«Проёб»dagi xabar kassa hisobotimi (ishga kelish sifatida sanalmaydi — kechki hisobot)."""
    try:
        _tag, body, _name = split_tag(db, text or "")
        lo = amount_floor(body)
        return is_report_like(body) and any(line_amounts(ln, lo) for ln in body.splitlines())
    except Exception:
        return False


AMOUNT_MIN = 300        # «Rd» siz matnda — 300 dan kichik son summa emas
AMOUNT_MIN_RD = 100     # «Rd 04.11» li achotda va 🔗 chekda 3 xonali summa ham chek («39)290» — egasi, 2026-11-04)


def amount_floor(text: str) -> int:
    return AMOUNT_MIN_RD if has_rd(text) else AMOUNT_MIN


def line_amounts(line: str, lo: int = AMOUNT_MIN) -> list[int]:
    if TOTAL_RE.search(line):
        return []
    body = line.rsplit("=", 1)[0] if "=" in line else line
    body = TIME_RE.sub(" ", DATE_RE.sub(" ", RD_FIND.sub(" ", body)))
    out = []
    for m in NUM_RE.finditer(body):
        v = int(re.sub(r"\D", "", m.group(1)))
        if lo <= v <= 99999:
            out.append(v)
    return out


def parse_report_ex(text: str, ref=None) -> list[tuple[dt.date, int, str | None]]:
    """Hisobot kuni = 'Rd dd.mm' (chekdan keyingi qatorda, shu qatorda yoki sarlavhada). Rd yo'q — ref (yozilgan kun).
    -> [(kun, summa, RD raqami | None)] — RD raqami «Rd3 04.11» dan (🎯 bonus har RD uchun alohida)."""
    ref = ref or dt.date.today()
    lo = amount_floor(text)
    ents = [(find_rd(line, ref), find_rd_no(line), line_amounts(line, lo)) for line in text.splitlines()]
    mode, seen = "suffix", False
    for rd, _no, amts in ents:
        if rd and not amts:
            mode = "suffix" if seen else "header"
            break
        if amts:
            seen = True
    slots, pending, cur, cur_no = [], [], None, None
    for rd, no, amts in ents:
        if rd and amts:
            slots += [[rd, a, no] for a in amts]
            cur, cur_no = rd, no
        elif rd:
            if mode == "suffix":
                for i in pending:
                    slots[i][0], slots[i][2] = rd, no
                pending = []
            cur, cur_no = rd, no
        elif amts:
            for a in amts:
                if mode == "header" and cur:
                    slots.append([cur, a, cur_no])
                else:
                    slots.append([None, a, None])
                    pending.append(len(slots) - 1)
    fill = cur or ref
    return [(rd or fill, a, no) for rd, a, no in slots]


def parse_report(text: str, ref=None) -> list[tuple[dt.date, int]]:
    return [(d, a) for d, a, _no in parse_report_ex(text, ref)]


def report_checks_ex(text: str, post: dt.date, is_owner: bool) -> list[tuple[dt.date, int, str | None]]:
    out = parse_report_ex(text, post)
    if is_owner and out and not has_rd(text):
        lines = [(line_amounts(ln), set(parse_dates(ln, post))) for ln in text.splitlines()]
        filled = [x for x in lines if x[0]]
        if filled and all(x[1] for x in filled):
            common = set.intersection(*[x[1] for x in filled])
            if len(common) == 1:
                d = next(iter(common))
                return [(d, a, no) for _, a, no in out]
    return out


def report_checks(text: str, post: dt.date, is_owner: bool) -> list[tuple[dt.date, int]]:
    return [(d, a) for d, a, _no in report_checks_ex(text, post, is_owner)]


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


def adj_command(db: Database, text: str) -> bool:
    """Guruhdagi xabar — jarima/bonus BUYRUG'Imi («@baxa штраф 5», «Bayzed бонус 10»)? E'lon, qoida yoki uzun matn
    («bugun 10 000 kassa qilganga 20 $ бонус» kabi) — buyruq emas: bot uni o'qimaydi va hech kimdan so'ramaydi.
    Buyruq: qisqa (4 qatorgacha, har qatorda 6 tagacha so'z) va unda xodim ko'rsatilgan (@username yoki ism)."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if not lines or len(lines) > 4 or len(text) > 300:
        return False
    words = [len(re.findall(r"[A-Za-zА-Яа-яЁёЎўҚқҒғҲҳ']+", ln)) for ln in lines]
    if any(w > 6 for w in words):
        return False
    if len(lines) == 1 and words[0] <= 2:
        return True                                     # «бонус 10» — juda qisqa: kimga ekanini egasidan so'raydi
    if re.search(r"@[A-Za-z0-9_]{3,32}", text):
        return True
    return any(it["person_id"] for it in parse_adjustments(db, text))


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


def rename_opening(db: Database, old: str, new: str) -> None:
    """Xodim ismi o'zgardi — boshlang'ich kassadagi ismi ham (umumiy reyting ikkiga bo'linib qolmasin)."""
    if not old or not new or not db.one("SELECT 1 FROM opening WHERE name=?", (old,)):
        return
    if old.lower() != new.lower() and db.one("SELECT 1 FROM opening WHERE name=?", (new,)):
        return                                             # bu ism allaqachon bor — tegmaymiz
    db.run("UPDATE opening SET name=? WHERE name=?", (new, old))


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
    keep: dict = {}                                     # tahrir: eski nusxadagi «🔁 Kim ishladi» (kun bo'yicha) qoladi
    if msg_id is not None:
        for o in db.all("SELECT id, person_id, status FROM reports WHERE chat_id=? AND msg_id=?", (chat_id, msg_id)):
            if o["status"] == "done":                   # guruhda xabar tahrirlandi: eski raqamlar tarixda qoladi
                old = amounts_of(db, o["id"])
                days = report_days(db, o["id"])
                log(db, "rep_edit", o["person_id"] or person_id, days[0] if days else None, o["id"],
                    amounts_text(old), amounts_text(c[1] for c in checks))
            if o["person_id"] == person_id:
                for x in db.all("SELECT rd, pay FROM checks WHERE report_id=?", (o["id"],)):
                    keep.setdefault(x["rd"], set()).add(x["pay"])
            delete_report(db, o["id"])
    rid = int(db.run("INSERT INTO reports(person_id, chat_id, msg_id, sender_id, sender_name, raw, created) "
                     "VALUES(?,?,?,?,?,?,?)", (person_id, chat_id, msg_id, sender_id, sender_name, raw,
                                               dt.datetime.now().isoformat())).lastrowid)
    for c in checks:                                    # (kun, summa) yoki (kun, summa, RD raqami)
        rd, amt, no = c[0], c[1], (c[2] if len(c) > 2 else None)
        d = iso(rd) if rd else None
        was = keep.get(d) or set()
        pay = next(iter(was)) if len(was) == 1 else None
        db.run("INSERT INTO checks(report_id, rd, amount, usd, pay, rd_no) VALUES(?,?,?,?,?,?)",
               (rid, d, amt, price_for(db, amt), pay, no))
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


def date_issue(db: Database, rid: int, today: dt.date) -> dict | None:
    """⚠️ Sana xato bo'lishi mumkin (faqat «Проёб»dagi hisobot, bir marta so'raladi):
    * odd — bitta-ikkita chek qolganlaridan boshqa sanada (2+ kun farq): «1950 — 25.10, qolganlari 29.10»;
    * old — hamma chek bugun/kechadan eski sanada.
    -> {"kind", "main" (iso), "odd": [checks]} yoki None. Hisobot mantiqiga boshqa tegilmaydi."""
    r = report(db, rid)
    if r is None or r["date_ok"] or not r["chat_id"] or r["chat_id"] > 0:
        return None
    rows = db.all("SELECT id, rd, amount FROM checks WHERE report_id=? AND rd IS NOT NULL AND skip=0 ORDER BY id", (rid,))
    if not rows:
        return None
    from collections import Counter
    cnt = Counter(x["rd"] for x in rows)
    main, n_main = sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0] != max(cnt)))[0]
    main_d = dt.date.fromisoformat(main)
    if len(cnt) >= 2 and n_main >= 2:
        odd = [x for x in rows if x["rd"] != main and cnt[x["rd"]] <= max(1, len(rows) // 3)
               and abs((dt.date.fromisoformat(x["rd"]) - main_d).days) >= 2]
        if odd:
            return {"kind": "odd", "main": main, "odd": odd}
    if all(dt.date.fromisoformat(x["rd"]) < today - dt.timedelta(days=1) for x in rows):
        return {"kind": "old", "main": main, "odd": rows}
    return None


def pending_reports(db: Database) -> list[int]:
    return [r["id"] for r in db.all("SELECT id FROM reports WHERE status='pending' ORDER BY id")]


def report_days(db: Database, rid: int) -> list[str]:
    return [r["rd"] for r in db.all("SELECT DISTINCT rd FROM checks WHERE report_id=? AND rd IS NOT NULL ORDER BY rd",
                                    (rid,))]


def gaz_batches(db: Database, pids, day: str) -> list[list[int]]:
    """🔗 Xodimning shu kun uchun /gaz achotlari: har /gaz chaqiruvi — o'z cheklari (wchecks.reported_ts bo'yicha)."""
    out = []
    for pid in {x for x in pids if x}:
        by: dict = {}
        for x in db.all("SELECT reported_ts, amount FROM wchecks WHERE person_id=? AND day=? AND deleted=0 "
                        "AND reported_ts IS NOT NULL", (pid, day)):
            by.setdefault(x["reported_ts"], []).append(int(x["amount"]))
        out += [sorted(v) for v in by.values()]
    return out


def supersede(db: Database, rid: int) -> list[dict]:
    """Yangi hisobot eskisini to'liq o'z ichiga olsa (>=2 chek) — eskisi hisobdan chiqadi.
    🔗 /gaz achoti (bitta kun, summalari xodimning bitta /gaz idagi bilan aynan bir xil) — yangi cheklar: eski
    hisobotlar almashtirilmaydi, summalar tasodifan mos kelsa ham (egasi, 2026-11-11: kunlar aralashib, ikki marta
    sanaldi). Faqat o'sha achot ikkinchi marta tashlansa (shunday hisobotlar /gaz lardan ko'p) — takror."""
    r = report(db, rid)
    new = amounts_of(db, rid)
    days = report_days(db, rid)
    gaz = None
    if len(days) == 1 and new:
        sender = P.by_tg(db, r["sender_id"]) if r["sender_id"] else None
        batches = gaz_batches(db, (r["person_id"], sender["id"] if sender else None), days[0])
        if sorted(new) in batches:
            gaz = (sorted(new), batches.count(sorted(new)))
    out = []
    for d in days:
        olds = db.all("SELECT DISTINCT r.id FROM reports r JOIN checks c ON c.report_id=r.id "
                      "WHERE r.person_id=? AND r.status='done' AND r.id<>? AND c.rd=? ORDER BY r.id",
                      (r["person_id"], rid, d))
        if gaz is not None:
            sig, nb = gaz
            same = [o["id"] for o in olds if sorted(amounts_of(db, o["id"])) == sig]
            if len(same) >= nb:                             # shu /gaz achoti oldin ham tashlangan — takror
                if len(sig) >= 2:
                    set_report_status(db, same[-1], "replaced")
                    out.append({"old": same[-1], "amounts": sig, "kind": "replace"})
                else:
                    out.append({"old": same[-1], "amounts": sig, "kind": "dup"})
            continue
        for o in olds:
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


def stand_in(db: Database, pid: int, day: str) -> int | None:
    """Shu kuni pid o'rniga kim ishlagan: pid akkauntidagi hamma cheklar bitta boshqa odamniki («🔁 Kim ishladi») va
    pid o'zi o'sha kuni hech qayerda ishlamagan bo'lsa — o'sha odam (jarima/bonus unga o'tadi; calc bilan bir xil)."""
    ws = {x["w"] for x in db.all("SELECT DISTINCT COALESCE(ch.pay, r.person_id) w FROM checks ch JOIN reports r "
                                 "ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 AND ch.rd=? "
                                 "AND r.person_id=?", (iso(day), pid)) if x["w"] is not None}
    if len(ws) != 1 or pid in ws:
        return None
    if db.one("SELECT 1 FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 "
              "AND ch.rd=? AND ch.pay=?", (iso(day), pid)):
        return None                                        # o'zi boshqa akkauntda ishlagan
    w = P.person(db, next(iter(ws)))
    return w["id"] if w is not None and w["kassa_kind"] in PAYABLE else None


def report_worker(db: Database, rid: int) -> int | None:
    """Hisobot kimning ishi: cheklarining hammasi bitta odamniki («Kim ishladi» yoki akkaunt egasi) bo'lsa — o'sha."""
    ws = {x["w"] for x in db.all("SELECT DISTINCT COALESCE(ch.pay, r.person_id) w FROM checks ch JOIN reports r "
                                 "ON r.id=ch.report_id WHERE ch.report_id=? AND ch.skip=0", (rid,))}
    if len(ws) != 1 or None in ws:
        return None
    w = P.person(db, next(iter(ws)))
    return w["id"] if w is not None and w["kassa_kind"] in PAYABLE else None


def set_pay_report(db: Database, rid: int, pid) -> None:
    db.run("UPDATE checks SET pay=? WHERE report_id=? AND pay IS NULL", (pid, rid))


def day_pay(db: Database, acct: int, day: str, skip_rid: int = 0) -> int | None:
    """Shu akkauntning shu kuni «🔁 Kim ishladi» belgisi: qabul qilingan hamma cheklari bitta boshqa odamniki bo'lsa —
    o'sha odam. Keyin kelgan chek (to'liqroq hisobot, qo'lda qo'shilgan) ham unga (egasi, 2026-11-04)."""
    pays = {x["pay"] for x in db.all("SELECT DISTINCT ch.pay FROM checks ch JOIN reports r ON r.id=ch.report_id "
                                     "WHERE r.person_id=? AND r.status='done' AND ch.rd=? AND r.id<>?",
                                     (acct, iso(day), skip_rid))}
    return next(iter(pays)) if len(pays) == 1 and None not in pays else None


def day_pay_pct(db: Database, acct: int, day: str, skip_rid: int = 0):
    """«🔁 Kim ishladi» — Artur bo'lsa, o'sha kun uchun yozilgan foizi (bitta bo'lsa). Yo'q — None."""
    v = {x["pay_pct"] for x in db.all("SELECT DISTINCT ch.pay_pct FROM checks ch JOIN reports r ON r.id=ch.report_id "
                                      "WHERE r.person_id=? AND r.status='done' AND ch.rd=? AND r.id<>?",
                                      (acct, iso(day), skip_rid))}
    return next(iter(v)) if len(v) == 1 else None


def inherit_pay(db: Database, rid: int) -> None:
    """Hisobotning «kim ishladi» belgilanmagan cheklariga — o'sha kunning belgisi (umumiy akkauntda har hisobot o'zi
    so'raladi — tegilmaydi)."""
    r = report(db, rid)
    if r is None or not r["person_id"] or is_pool(db, r["person_id"]):
        return
    for d in report_days(db, rid):
        w = day_pay(db, r["person_id"], d, rid)
        if w is not None:
            db.run("UPDATE checks SET pay=?, pay_pct=? WHERE report_id=? AND rd=? AND pay IS NULL",
                   (w, day_pay_pct(db, r["person_id"], d, rid), rid, d))


def set_pay_day(db: Database, acct: int, day: str, pid, pct: float | None = None) -> None:
    """Shu akkauntning shu kundagi hamma cheklari uchun zp oluvchi (None = akkaunt egasi). pct — 🤝 Artur o'zi
    ishlagan bo'lsa, shu kun uchun uning foizi (egasi, 2026-11-12)."""
    log(db, "pay_day", acct, day, pid, "", f"{pid or ''}{f' {pct:g}%' if pct is not None else ''}")
    db.run("UPDATE checks SET pay=?, pay_pct=? WHERE rd=? AND report_id IN (SELECT id FROM reports WHERE person_id=? "
           "AND status='done')", (pid, pct, day, acct))


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
    w = None if is_pool(db, pid) else day_pay(db, pid, day)     # kun «🔁 Kim ishladi» bilan belgilangan bo'lsa — unga
    wp = day_pay_pct(db, pid, day) if w is not None else None
    rid = db.run("INSERT INTO reports(person_id, chat_id, sender_name, raw, status, created) VALUES(?,?,?,?,?,?)",
                 (pid, 0, "вручную", str(amount), "done", dt.datetime.now().isoformat())).lastrowid
    cid = db.run("INSERT INTO checks(report_id, rd, amount, usd, pay, pay_pct) VALUES(?,?,?,?,?,?)",
                 (rid, day, amount, price_for(db, amount), w, wp)).lastrowid
    log(db, "chk_add", pid, day, cid, "", amount)


def delete_check(db: Database, cid: int) -> None:
    """Chekni o'chirish (xodim botdagi chekini o'chirdi — kassadagisi ham; tarixda qoladi)."""
    c = check_row(db, cid)
    db.run("DELETE FROM checks WHERE id=?", (cid,))
    if c is not None:
        log(db, "chk_del", c["acct"], c["rd"], cid, c["amount"], "")


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
    selfs = [pid for pid, p in ps.items() if p["kassa_kind"] == "self"]
    self_usd: dict = {}                      # akkaunt -> shu haftada siz o'zingiz ishlagan cheklar ($)
    if selfs:
        q = ",".join("?" * len(selfs))
        for row in db.all(f"SELECT r.person_id acct, COALESCE(SUM(ch.usd),0) usd FROM checks ch JOIN reports r "
                          f"ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ? "
                          f"AND ch.pay IN ({q}) GROUP BY r.person_id", [w0, w1] + selfs):
            self_usd[row["acct"]] = float(row["usd"])
    self_pct = percent_on(db, selfs[0], week) if selfs else None
    stand: dict = {}                         # akkaunt -> [(xodim, $)] — o'rniga boshqa xodim ishlagan cheklar
    for row in db.all("SELECT r.person_id acct, ch.pay pay, COALESCE(SUM(ch.usd),0) usd FROM checks ch "
                      "JOIN reports r ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ? "
                      "AND ch.pay IS NOT NULL AND ch.pay<>r.person_id GROUP BY r.person_id, ch.pay", (w0, w1)):
        q = ps.get(row["pay"])
        if q is not None and q["kassa_kind"] == "worker":
            stand.setdefault(row["acct"], []).append((q, float(row["usd"])))
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
        op = raw_op = owner_pct_on(db, p["id"], week)
        if kind == "self" and op is None:
            op = 0.0
        it = {"pid": p["id"], "name": p["name"], "kind": kind, "n": a["n"], "usd": r2(a["usd"]), "raw": int(a["raw"]),
              "wpct": wp,
              "opct": op, "kshare": kassa_sh.get((p["id"], "partner"), 0.0),
              "kshare_owner": kassa_sh.get((p["id"], "owner"), 0.0), "zp_on": bool(p["zp_on"]),
              "self_usd": r2(self_usd.get(p["id"], 0.0)) if kind != "self" else 0.0, "self_pct": self_pct,
              "stand": []}
        if kind != "pool":                   # o'rniga ishlaganlar: zp — o'z foizi, «siz %» — o'z akkauntidagi foiz
            for q, u in sorted(stand.get(p["id"], []), key=lambda x: order.get(x[0]["id"], 10 ** 6)):
                qo = owner_pct_on(db, q["id"], week)
                it["stand"].append({"pid": q["id"], "name": q["name"], "usd": r2(u), "zp_on": bool(q["zp_on"]),
                                    "wpct": percent_on(db, q["id"], week),
                                    "opct": None if raw_op is None else (raw_op if qo is None else qo)})
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


# ───────────────────────── 🎯 kunlik kassa bonusi — Arturniki (egasi, 2026-11-04)
def _limits(raw: str) -> list[tuple[float, float]]:
    """«20000=20 27000=30» -> [(20000, 20), (27000, 30)]."""
    out = []
    for p in (raw or "").replace(",", " ").split():
        a, _, b = p.partition("=")
        try:
            out.append((float(a), float(b)))
        except ValueError:
            continue
    return sorted(out)


def bonus_groups(db: Database, start, end) -> list[dict]:
    """🎯 Kassa bonusi har RD papka × kun alohida (egasi, 2026-11-04: Cred o'z RD si va Lazarus RD sida ishlasa —
    ikkalasining kassasi qo'shilmaydi). RD raqami hisobotdagi «Rd3 04.11» dan; raqamsiz hisobot — akkaunt bo'yicha.
    -> [{day, rd, acct, accts, raw, n, kassa, checks}] (bonussizlari ham)."""
    grp: dict = {}
    for c in db.all("SELECT ch.rd, ch.amount, ch.rd_no, r.person_id acct FROM checks ch JOIN reports r "
                    "ON r.id=ch.report_id WHERE r.status='done' AND ch.skip=0 AND ch.rd BETWEEN ? AND ? "
                    "AND r.person_id IS NOT NULL", (iso(start), iso(end))):
        key = (c["rd"], f"rd{c['rd_no']}" if c["rd_no"] else f"a{c['acct']}")
        g = grp.setdefault(key, {"day": c["rd"], "rd": c["rd_no"], "acct": None if c["rd_no"] else c["acct"],
                                 "raw": 0, "n": 0, "accts": set()})
        g["raw"] += int(c["amount"])
        g["n"] += 1
        g["accts"].add(c["acct"])
    out = []
    for g in grp.values():
        kb, cb = day_bonus(db, g["raw"], g["n"])
        out.append({**g, "accts": sorted(g["accts"]), "kassa": kb, "checks": cb})
    return sorted(out, key=lambda x: (x["day"], int(x["rd"]) if x["rd"] else 99, x["acct"] or 0))


def day_bonus(db: Database, raw: int, n: int) -> tuple[float, float]:
    """Bir akkauntning bir kunlik bonusi: (kassa uchun, chek soni uchun) $. Kassa 20 000 va undan ko'p — 20 $,
    27 000 va undan ko'p — 30 $ (20 o'rniga); 11 va undan ko'p chek — yana 15 $. Bonus Arturga qo'shiladi (haftalik
    hisobda ham), xodimlarga daxli yo'q va faqat egasi ko'radi."""
    kb = cb = 0.0
    for lim, usd in _limits(db.get("kbonus_kassa")):
        if raw >= lim:
            kb = usd
    for lim, usd in _limits(db.get("kbonus_checks")):
        if n >= lim:
            cb = usd
    return kb, cb


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
            "moved": [],                     # o'rniga ishlaganga o'tgan jarima/bonuslar (hisobga kirmaydi, faqat ko'rinadi)
            "outs": [], "ins": [], "tr_out": 0.0, "tr_in": 0.0,
            "sin": [], "sout": [], "sin_sum": 0.0, "sout_sum": 0.0,
            "total": None, "share_part": 0.0, "pf": 0.0, "pb": 0.0,
            "work_zp": 0.0}                  # 🤝 Artur o'zi ishlagan kunlar uchun (o'z foizi bilan)


def calc(db: Database, start: dt.date, end: dt.date) -> dict:
    """Davr bo'yicha hamma narsa. -> {'rows': {pid: row}, 'order': [...], 'K', 'raw', 'n', 'owner': {...}}

    Har akkaunt kassasi (kun bo'yicha) shunday bo'linadi:
    * haftalik foizlar kiritilgan (owner_pct bor): ishlagan xodim % + siz % → qolgani Arturga. Akkauntda siz o'zingiz
      ishlagan cheklar ($) — sizga o'z % ingiz, qolgani Arturga; ulardan «siz %» olinmaydi (egasi, 2026-11-02:
      Bayzed 621 $, siz ishlagan 372 $: 372 × 50% + (621 − 372) × 14% = 186 + 34.86). Akkauntda o'rniga boshqa
      xodim ishlagan bo'lsa — o'sha qismdan «siz %» ishlagan xodimning o'z akkauntidagi foiz (egasi, 2026-11-04);
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

    checks = db.all("SELECT ch.id cid, ch.rd, ch.amount, ch.usd, ch.skip, ch.pay, ch.pay_pct, r.person_id acct "
                    "FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE r.status='done' AND ch.rd BETWEEN ? AND ? "
                    "ORDER BY ch.rd, ch.id", (s, e))
    base_zp: dict = {}               # (pid, day) -> zp (o'tkazma va zp-ulush uchun)
    opp_acc: dict = {}               # (acct, kim ishlagan | None, «siz %») -> $ — 📈 egasi ulushi qayerdan
    acct_usd_day: dict = {}          # (acct, day) -> usd
    zp_ad: dict = {}                 # (acct, day) -> {"all", "on", "self", "off", "self_usd"} — shu akkaunt cheklaridan zp
    day_payees: dict = {}            # (acct, day) -> shu akkauntda shu kuni kimlar ishlagan (zp oluvchilar)
    worked: set = set()              # (pid, day) — shu kuni biror akkauntda ishlagan
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
        # 📈 egasi ulushi (egasi, 2026-11-12: «Cred 288 × 20% = …»): boshqalar ishlagan chekdan — «siz %»; o'rniga
        # boshqa xodim ishlagan bo'lsa — o'sha xodimning o'z akkauntidagi foizi (op_fix bilan bir xil)
        if payee is None or payee not in rows or rows[payee]["kind"] != "self":
            oa = opct(c["acct"], d)
            ow = opct(payee, d) if payee in rows and payee != c["acct"] and a["kind"] != "pool" else None
            use = ow if (ow is not None and oa is not None) else oa
            if use is not None:
                k = (c["acct"], payee if payee in rows and payee != c["acct"] else None, float(use))
                opp_acc[k] = opp_acc.get(k, 0.0) + usd
        if payee is None or payee not in rows:
            a["unassigned"] += 1
            continue
        day_payees.setdefault((c["acct"], d), set()).add(payee)
        worked.add((payee, d))
        pr = rows[payee]
        # 🤝 Artur o'zi ishlagan kun — «🔁 Kim ishladi» da yozilgan foizi (uning ulush foizi emas)
        pp = (c["pay_pct"] or 0.0) if pr["kind"] == "partner" else pct(payee, d)
        key = (c["acct"], pp)
        pr["earn"][key] = pr["earn"].get(key, 0.0) + usd
        z = usd * pp / 100
        base_zp[(payee, d)] = base_zp.get((payee, d), 0.0) + z
        bucket = zp_ad.setdefault((c["acct"], d), {"all": 0.0, "on": 0.0, "self": 0.0, "off": 0.0, "self_usd": 0.0,
                                                   "op_fix": 0.0})
        bucket["all"] += z
        if pr["kind"] == "self":
            bucket["self"] += z
            bucket["self_usd"] += usd                  # siz o'zingiz ishlagan cheklar ($)
        elif pr["zp_on"] or pr["kind"] == "partner":
            bucket["on"] += z
        else:
            bucket["off"] += z
        if pr["kind"] != "self" and payee != c["acct"] and a["kind"] != "pool":
            # o'rniga ishlagan: «siz %» — ishlagan odamning o'z akkauntidagi foiz (egasi, 2026-11-04: Adam o'rniga
            # Cred ishlasa — 125 × 20% (Credniki), 14% (Adamniki) emas). Uning foizi yo'q bo'lsa — akkauntniki.
            ow, oa = opct(payee, d), opct(c["acct"], d)
            if ow is not None and oa is not None:
                bucket["op_fix"] += usd * (ow - oa) / 100
        if payee != c["acct"]:
            a["paid_out"][payee] = a["paid_out"].get(payee, 0.0) + usd
            name = ps[payee]["name"]
            if name not in day["ops"]:
                day["ops"].append(name)

    for pid, r in rows.items():
        if r["kind"] in PAYABLE:
            r["zp"] = r2(sum(u * p / 100 for (_acct, p), u in r["earn"].items()))
        elif r["kind"] == "partner":
            r["work_zp"] = r2(sum(u * p / 100 for (_acct, p), u in r["earn"].items()))

    # 🎯 kunlik kassa bonuslari (har RD papka × kun alohida) — Arturga
    kb_items = [g for g in bonus_groups(db, start, end) if (g["kassa"] or g["checks"]) and
                any(a in rows for a in g["accts"])]
    kbonus = r2(sum(x["kassa"] + x["checks"] for x in kb_items)) if partner is not None else 0.0

    # jarima / bonus / avans
    rd_of: dict = {}                 # odam (akkaunt) -> papkalari (RD): «RD 7, RD 9» — hisobda qaysi papkadan ekani
    for x in db.all("SELECT fp.person_id pid, f.name FROM folder_people fp JOIN folders f ON f.id=fp.folder_id "
                    "ORDER BY lower(f.name)"):
        rd_of[x["pid"]] = f"{rd_of[x['pid']]}, {x['name']}" if x["pid"] in rd_of else x["name"]
    strike_rd = {x["adj_id"]: x["name"] for x in db.all(
        "SELECT s.adj_id, f.name FROM strikes s JOIN folders f ON f.id=s.folder_id WHERE s.adj_id IS NOT NULL "
        "AND s.day BETWEEN ? AND ?", (s, e))}       # zaderjka jarimasi qaysi RD da bo'lgan
    for a in db.all("SELECT * FROM adj WHERE cancelled=0 AND pending=0 AND day BETWEEN ? AND ? ORDER BY day, id",
                    (s, e)):
        pid = a["person_id"]
        key = {"fine": "fines", "bonus": "bonuses", "adv": "advs"}.get(a["kind"])
        item = {"usd": float(a["usd"]), "day": a["day"], "source": a["source"], "note": a["note"], "id": a["id"],
                "rd": strike_rd.get(a["id"], "")}
        ws = day_payees.get((pid, a["day"]))
        if a["kind"] in ("fine", "bonus") and a["source"] in MOVABLE and ws and len(ws) == 1 \
                and (pid, a["day"]) not in worked:             # o'zi shu kuni ishlamagan, akkauntida bittasi ishlagan
            to = next(iter(ws))
            if to in rows and rows[to]["kind"] in PAYABLE:
                if pid in rows:
                    rows[pid]["moved"].append({**item, "kind": a["kind"], "to": to, "to_name": ps[to]["name"]})
                item.update(via=pid, via_name=ps[pid]["name"] if pid in ps else "?", via_rd=rd_of.get(pid, ""))
                pid = to
        r = rows.get(pid)
        if r is None:
            continue
        if key:
            r[key].append(item)
    for r in rows.values():
        r["zp_parts"] = [{"acct": acct, "name": ps[acct]["name"], "rd": rd_of.get(acct, ""), "zp": r2(u * p / 100)}
                         for (acct, p), u in r["earn"].items()]     # zp qaysi RD/akkauntdan (xodimga xabar uchun)
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
    no_op: set = set()
    zero = {"all": 0.0, "on": 0.0, "self": 0.0, "off": 0.0, "self_usd": 0.0, "op_fix": 0.0}
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
                if rows[acct]["kind"] in ("worker", "pool"):
                    no_op.add(acct)                    # «siz %» yozilmagan — eski usulda (ogohlantiriladi)
        else:                                          # «siz %» — faqat boshqalar ishlagan qismidan
            art = u - z["all"] - (u - z["self_usd"]) * op / 100 - z["op_fix"]
            if u:
                modes.add("split")
        art_net = art - sh["partner"]
        mine = u - art - z["on"] - sh["owner"]
        x = acct_split.setdefault(acct, {"usd": 0.0, "artur": 0.0, "zp": 0.0, "share": 0.0, "pshare": 0.0,
                                         "mine": 0.0, "own": 0.0, "own_usd": 0.0})
        x["usd"] += u
        x["own"] += z["self"]                          # shundan — o'zingiz ishlaganingiz uchun (o'z % ingiz)
        x["own_usd"] += z["self_usd"]
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
            r["kbonus"] = kbonus                       # 🎯 kassa bonuslari ham Arturga (egasi, 2026-11-04)
            r["total"] = r2(r["share_part"] + pf - pb - r["fine"] + r["bonus"] - r["adv"] - r["tr_out"] + r["tr_in"]
                            + r["sin_sum"] + kbonus    # Arturga yozilgan ulush ham (egasi, 2026-11-04)
                            + r["work_zp"])            # o'zi ishlagan kunlar (egasi, 2026-11-12)

    K = r2(sum(acct_usd_day.values()))
    me = next((r for r in rows.values() if r["kind"] == "self"), None)
    per_acct = []
    for pid in [p for p in rows if p in acct_split]:
        x = acct_split[pid]
        per_acct.append({"pid": pid, "usd": r2(x["usd"]), "artur": r2(x["artur"]), "half": r2(x["usd"] - x["artur"]
                                                                                              - x["pshare"]),
                         "zp": r2(x["zp"]), "share": r2(x["share"]), "pshare": r2(x["pshare"]), "mine": r2(x["mine"]),
                         "own": r2(x["own"]), "own_usd": r2(x["own_usd"]), "self": rows[pid]["kind"] == "self",
                         "opp": [(pc, r2(u_), r2(u_ * pc / 100), via) for (ac, via, pc), u_ in sorted(
                             opp_acc.items(), key=lambda kv: (kv[0][1] is not None, kv[0][2])) if ac == pid and r2(u_)]})
    unknown = [r["p"]["name"] for r in rows.values() if r["kind"] == "worker" and not r["zp_on"] and r["earn"]]
    zps = r2(sum(r["zp"] for r in rows.values() if r["kind"] == "worker" and r["zp_on"]))
    owner_paid = r2(sum(x["share"] for x in acct_split.values()))
    partner_paid = r2(sum(x["pshare"] for x in acct_split.values()))
    share_part = rows[partner["id"]]["share_part"] if partner else 0.0
    out_self = me["tr_out"] if me else 0.0
    in_self = me["tr_in"] if me else 0.0
    mine = r2(sum(x["mine"] for x in acct_split.values()))
    # jarima/bonus (egasi, 2026-11-02): xodimga bonus — qo'shiladi, jarima — ayriladi; jarima Arturga qo'shiladi,
    # bonusni Artur to'laydi. Sizning o'z jarimangiz/bonusingiz ham Artur bilan; Artur yo'q bo'lsa — hammasi sizda.
    wf = r2(sum(r["fine"] for r in rows.values() if r["kind"] == "worker"))
    wb = r2(sum(r["bonus"] for r in rows.values() if r["kind"] == "worker"))
    # ulush: sizga yozilgani — daromadga, o'z zp ingizdan berganingiz — ayriladi (egasi, 2026-11-04: avval yo'qolardi)
    sin_self = me["sin_sum"] if me else 0.0
    sout_self = me["sout_sum"] if me else 0.0
    if partner is not None:
        income = r2(mine - out_self + in_self - (me["fine"] if me else 0.0) + (me["bonus"] if me else 0.0)
                    + sin_self - sout_self)
    else:
        income = r2(mine - out_self + in_self - wb + wf + sin_self - sout_self)
    mode = "split" if modes == {"split"} else ("legacy" if modes <= {"legacy"} else "mixed")
    owner = {"K": K, "partner_pct": partner_pct_of(db, partner, e) if mode == "legacy" else None, "mode": mode,
             "half": r2(K - share_part - partner_paid), "zps": zps, "owner_paid": owner_paid,
             "partner_paid": partner_paid, "out_self": r2(out_self), "in_self": r2(in_self), "income": income,
             "sin_self": r2(sin_self), "sout_self": r2(sout_self),
             # boshqa akkauntlarda «siz %» bor, bularda yo'q — eski usulda hisoblandi (egasi, 2026-11-04: ogohlantirish)
             "no_opct": [ps[x]["name"] for x in sorted(no_op, key=lambda x: ps[x]["name"].lower())]
             if "split" in modes else [], "no_opct_pp": partner_pct_of(db, partner, e) if partner else None,
             "kbonus": kbonus, "kbonus_items": kb_items if partner is not None else [],
             "mine": mine, "self_zp": me["zp"] if me else 0.0, "per_acct": per_acct, "unknown_zp": unknown,
             "partner_id": partner["id"] if partner else None,
             "partner_total": rows[partner["id"]]["total"] if partner else 0.0,
             "partner_share": share_part, "pf": pf, "pb": pb, "wf": wf, "wb": wb, "zps_paid": r2(zps + wb - wf),
             "partner_work": rows[partner["id"]]["work_zp"] if partner else 0.0}
    order = [p["id"] for p in P.people(db, active_only=False) if p["kassa_kind"]]
    return {"rows": rows, "order": order, "K": K, "raw": RAW, "n": N, "owner": owner, "names":
            {pid: p["name"] for pid, p in ps.items()}, "rds": rd_of}


def partner_pct_of(db: Database, partner, day) -> float:
    return percent_on(db, partner["id"], day) if partner else 50.0


def has_data(r: dict) -> bool:
    if r["kind"] == "partner":
        return r["share_part"] > 0 or bool(r["fines"] or r["bonuses"] or r["advs"] or r["outs"] or r["ins"]
                                           or r["earn"])
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
