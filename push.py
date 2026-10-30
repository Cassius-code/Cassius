"""Push: issiq lidlarga xabar — har papka o'z Push akkauntidan, faqat qo'lda (🌅 / ☀️ tugma).

Kimga va qaysi tartibda — egasi tugma bilan tanlaydi (soatga qaramaydi; soat 15:00 da ham 🌅 bo'lishi mumkin):
* 🌅 Ertalabki: bugun gaplashmaganlar — kecha yozganlardan boshlab eskiroqlariga (lidning oxirgi o'zi yozgani
  bo'yicha, yangisi oldin).
* ☀️ Kunduzgi: avval bugun gaplashganlar — 1) ertalab gaplashganlar, 2) belgilangan vaqtdan (30 daq / 1 soat) beri
  jim turganlar; ular tugasa — kechagi, keyin eskiroqlar. Hozir gaplashayotganlarga (shu vaqt ichida yozishganlarga) — YO'Q.
📚 Har Push — raqam: bitta raqamli Push bitta lidga hech qachon ikki marta ketmaydi (boshqa raqam — ketishi mumkin,
3 soat oralig'i bilan). Har papkaga — egasi yozgan son, AYNAN shuncha (yuborib bo'lmaganining o'rniga keyingi lid).
🧪 Haqiqiy ta'sir (yoqilsa): har 10 lidning 1 tasiga yuborilmaydi — ular o'zi yozdimi, taqqoslanadi (o'rniga boshqasi).
Baza: faqat belgilangan sanadan (28.08.2026) beri o'zi yozgan lidlar; davr — oxirgi N kun yoki sana oralig'i.
«Gaplashdi» — mijoz yoki xodim yozgan (Push xabarlari hisobga kirmaydi). ⚡/💊 yo'q; stavkasi tugamagan yangi
lidga yo'q; 3 soat ichida qayta yo'q.
"""
from __future__ import annotations

import asyncio
import os
import logging
import random
import time
from collections import deque
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from . import people as P
from . import push_lib as L
from .db import Database
from .rules import label_excluded, skip_list
from .tgsend import SendAbort, SendSkip, SendWait
from .timeutil import day_start, parse_date, parse_hhmm

log = logging.getLogger("push")

MIN_REPEAT = 180
_SENDING: dict[tuple[int, int], float] = {}     # (chat, topic) -> Push yuborila boshlagan vaqt


def sending_now(chat_id: int, topic_id: int) -> bool:
    """Shu topikka hozir Push yuborilyaptimi (asosiy akkaunt o'z xabarimizni «xodim javobi» demasin)."""
    t0 = _SENDING.get((int(chat_id), int(topic_id)))
    return t0 is not None and time.monotonic() - t0 < 120

RESUME_WINDOW = 30 * 60      # bot qayta ishga tushsa: shuncha vaqt ichida uzilgan Push joyidan davom etadi
LEGACY_GAP = 120             # eski versiya to'xtashda Push'ni «stopped» deb yozardi: yangilanishdan shuncha oldingisi
ACCOUNT_WAIT = 180           # davom ettirishdan oldin Push akkauntlari ulanishini kutish (soniya)
MAX_WAIT = 30 * 60           # Telegram «kuting» desa (FloodWait): shungacha papka kutib, keyin o'zi davom etadi
MAX_WAITS = 2                # bitta Push'da bir akkaunt necha marta kutadi (keyin — papka to'xtaydi)
CONTINUE_HOURS = 12          # «▶️ Davom ettirish» — Push tugaganidan keyin shuncha soat ichida
SPEEDS = {"fast": (1.0, 2.0), "normal": (2.0, 3.0), "slow": (3.0, 5.0)}
PROGRESS_EVERY = 5
SLOTS = ("morning", "day")
CONTROL_EVERY = 10           # 🧪 nazorat guruhi: har 10 lidning 1 tasi
CONTROL_KEEP = 24 * 3600     # nazorat guruhidagi lidga o'sha Push shuncha vaqt yuborilmaydi (o'lchov buzilmasin)
MAX_ERRORS = 5               # ketma-ket shuncha noma'lum xato — akkaunt to'xtaydi (cheksiz aylanmasin)


def held_out(bid: int, chat_id: int, topic_id: int) -> bool:
    """🧪 Shu lid nazorat guruhidami (har Push uchun o'zgarmas, ~10%)."""
    import hashlib
    h = hashlib.sha256(f"{bid}:{chat_id}:{topic_id}".encode()).digest()
    return h[0] % CONTROL_EVERY == 0


def _hm(raw: str) -> int | None:
    try:
        t = parse_hhmm(raw)
        return t.hour * 60 + t.minute
    except (ValueError, TypeError):
        return None


def push_times(db: Database) -> list[str]:                 # eski sozlama (endi ishlatilmaydi)
    return []


def slot_bounds(db: Database) -> tuple[int, int]:
    """(ertalab tugashi, kechqurun boshlanishi) — daqiqalarda."""
    m = _hm(db.get("push_morning_until") or "") or 13 * 60
    e = _hm(db.get("push_evening_from") or "") or 19 * 60
    return (m, e) if m < e else (13 * 60, 19 * 60)


def slot_at(db: Database, minute: int) -> str:
    m, e = slot_bounds(db)
    return "morning" if minute < m else ("evening" if minute >= e else "day")


def hhmm(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


# Baza: shu sanadan keyin o'zi (mijoz) yozgan HAR bir lid — yangi kelgani ham, eskisi ham (yozdi — aloqada).
# so'rovda: threads th (+ LEFT JOIN topics t).
BASE_SQL = "th.last_seen >= ?"


def spam_limited(db, acc_id) -> bool:
    """@SpamBot tekshiruvi: akkauntga Telegram spam-cheklov qo'yganmi (shu akkauntdan Push yuborilmaydi)."""
    if acc_id == -1:
        return db.get("main_spam") == "limited"
    row = db.one("SELECT spam FROM accounts WHERE id=?", (acc_id,)) if acc_id else None
    return bool(row and row["spam"] == "limited")


def base_count(db, base_ts: int, folder_id: int | None = None, active_since: int = 0) -> int:
    """Push bazasidagi lidlar soni (papka bo'yicha yoki hammasi); active_since — shu vaqtdan keyin o'zi yozganlar."""
    q = ("SELECT COUNT(*) FROM threads th JOIN chats c ON c.chat_id=th.chat_id "
         "LEFT JOIN topics t ON t.chat_id=th.chat_id AND t.topic_id=th.topic_id "
         "WHERE th.first_seen IS NOT NULL AND " + BASE_SQL + " AND th.last_seen>=?")
    args = [base_ts, active_since]
    if folder_id is not None:
        q += " AND c.folder_id=?"
        args.append(folder_id)
    return db.scalar(q, tuple(args))


class Pusher:
    def __init__(self, db: Database, tz: ZoneInfo, notifier, pool, tracker, sleep=asyncio.sleep, clock=time.time):
        self.db, self.tz, self.notifier, self.pool, self.tracker = db, tz, notifier, pool, tracker
        self._sleep, self.clock = sleep, clock
        self.running = False
        self._stop = False
        self._halt = False                       # bot to'xtayapti (yangilanish) — Push «uzildi», keyin davom etadi
        self._workers: list = []
        self._progress, self._live = "", None
        self.progress_text = ""                  # «120/300 · ✖️2» — ketayotgan Push (panel o'zi o'qiydi)
        self.last_report: tuple | None = None    # (tugagan vaqt, natija) — oxirgi Push

    @property
    def progress_text(self) -> str:
        """Ketayotgan Push: «yuborildi/jami». Jami — hozirgi son bilan (Push paytida o'zgartirilsa ham darhol)."""
        if self._live is not None:
            try:
                return self._live()
            except Exception:
                pass
        return self._progress

    @progress_text.setter
    def progress_text(self, value: str) -> None:
        self._progress, self._live = value, None

    # ------------------------------------------------------------ mazmun (📚 hozirgi Push)
    def current(self):
        return L.current(self.db)

    def media(self) -> dict | None:
        return L.media_of(self.current())

    def has_content(self) -> bool:
        return L.has_content(self.current())

    def base_from(self) -> int:
        """Baza: shu sanadan keyin o'zi (mijoz) yozgan lidlar — yangi kelgani ham, eskisi ham."""
        raw = self.db.get("push_base_from") or "2026-08-28"
        try:
            return int(datetime.combine(parse_date(raw), dtime(0, 0), tzinfo=self.tz).timestamp())
        except ValueError:
            return 0

    def window(self, now: int) -> tuple[int, int]:
        """Davr: lidning oxirgi o'z xabari shu oraliqda bo'lsin. Baza (qachon kelgan) — alohida shart."""
        lo, hi = 0, 2 ** 31
        days = self.db.get_int("push_days")
        if days > 0:
            lo = max(lo, day_start(now, self.tz) - (days - 1) * 86400)
        for key, edge in (("push_range_from", "lo"), ("push_range_to", "hi")):
            raw = self.db.get(key)
            if not raw:
                continue
            try:
                d = parse_date(raw)
            except ValueError:
                continue
            ts = int(datetime.combine(d, dtime(0, 0), tzinfo=self.tz).timestamp())
            if edge == "lo":
                lo = max(lo, ts)
            else:
                hi = min(hi, ts + 86400 - 1)
        return lo, hi

    def slot(self, now: int | None = None) -> str:
        """Eski (soatga qarab) — endi faqat tugma tanlanmagan holatlar uchun (eski uzilgan Push)."""
        now = int(self.clock() if now is None else now)
        t = datetime.fromtimestamp(now, self.tz)
        return "morning" if slot_at(self.db, t.hour * 60 + t.minute) == "morning" else "day"

    def _push_emojis(self) -> list[str]:
        return [ch for ch in self.db.get("push_emojis") if not ch.isspace() and ch not in ",;️‍"]

    # ------------------------------------------------------------ kimga
    def audience(self, slot: str | None = None, now: int | None = None, push_id: int | None = None) -> dict:
        now = int(self.clock() if now is None else now)
        evening = slot == "evening"                      # 🌙 kechki — tartib ☀️ dagidek (egasi, 2026-10-30)
        slot = "morning" if slot == "morning" else ("day" if slot in ("day", "evening") else self.slot(now))
        if push_id is None:
            cur = self.current()
            push_id = cur["id"] if cur is not None else 0
        cmap = P.chat_folder_map(self.db)
        folders = {f["id"]: f for f in P.folders(self.db)}
        allowed = {fid for fid, f in folders.items() if f["push_on"]}
        no_account = sorted(fid for fid in allowed if not folders[fid]["push_account_id"])
        allowed -= set(no_account)
        skip, push_e = skip_list(self.db), self._push_emojis()
        rows = self.db.all(
            "SELECT th.*, CASE WHEN th.topic_id<>0 THEN TRIM(COALESCE(t.icon,'') || ' ' || COALESCE(t.title,'')) "
            "ELSE COALESCE(c.title,'') END AS label, COALESCE(t.created_ts, th.first_seen) AS born "
            "FROM threads th JOIN chats c ON c.chat_id=th.chat_id "
            "LEFT JOIN topics t ON t.chat_id=th.chat_id AND t.topic_id=th.topic_id "
            "WHERE th.first_seen IS NOT NULL AND " + BASE_SQL + " AND th.last_seen BETWEEN ? AND ?",
            (self.base_from(),) + self.window(now))
        rows = [r for r in rows if cmap.get(r["chat_id"]) in allowed and not label_excluded(r["label"], skip)
                and (not push_e or label_excluded(r["label"], push_e))]
        matched = len(rows)
        fresh_n = max(0, self.db.get_int("push_newlead_minutes"))
        border = now - fresh_n * 60
        kept = [r for r in rows if r["stavka"] != "on" and (not fresh_n or r["born"] <= border)]
        fresh, rows = len(rows) - len(kept), kept
        got = {(x["chat_id"], x["topic_id"]) for x in self.db.all(
            "SELECT chat_id, topic_id FROM push_got WHERE push_id=? AND (held=0 OR ts>?)",
            (push_id or 0, now - CONTROL_KEEP))} if push_id else set()
        kept = [r for r in rows if (r["chat_id"], r["topic_id"]) not in got]     # 📚 shu raqamni olgan — hech qachon
        got_before, rows = len(rows) - len(kept), kept
        repeat = max(MIN_REPEAT, self.db.get_int("push_repeat_minutes"))
        kept = [r for r in rows if not r["last_push_ts"] or r["last_push_ts"] <= now - repeat * 60]
        repeated, rows = len(rows) - len(kept), kept

        today = day_start(now, self.tz)
        idle = max(0, self.db.get_int("push_idle_minutes"))
        quiet_border = now - idle * 60

        def talk(r) -> int:                                 # oxirgi suhbat: mijoz yoki xodim (Push emas)
            return max(r["last_seen"] or 0, r["last_staff_ts"] or 0)

        m_end, _e = slot_bounds(self.db)
        morning_talk = {(x["chat_id"], x["topic_id"]) for x in self.db.all(
            "SELECT DISTINCT chat_id, topic_id FROM journal WHERE ts BETWEEN ? AND ? AND who IN ('client','staff')",
            (today, min(today + m_end * 60, now)))}

        def group(r) -> int:
            """0 — ertalab gaplashgan, 1 — jim turgan, 2 — hozirgina yozishgan, 3 — bugun gaplashmagan."""
            if talk(r) < today:
                return 3
            if idle and talk(r) > quiet_border:
                return 2
            return 0 if (r["chat_id"], r["topic_id"]) in morning_talk else 1

        busy = sum(1 for r in rows if group(r) == 2)
        rows = [r for r in rows if group(r) != 2]          # hozir gaplashayotganlarga — hech qachon
        if slot == "morning":
            rows = [r for r in rows if group(r) == 3]      # bugun gaplashmaganlar: kecha → eskiroq (yangisi oldin)

            def key(r):
                return (-(r["last_seen"] or 0),)
        else:                                              # ☀️ bugungilar, keyin kecha → eskiroq

            def key(r):
                g = group(r)
                return (g, -(r["last_seen"] or 0))         # har guruhda: lid oxirgi yozgani, yangisi oldin
        rows.sort(key=key)
        limit = max(0, self.db.get_int("push_limit"))
        by_f: dict[int, list] = {}
        for r in rows:
            by_f.setdefault(cmap[r["chat_id"]], []).append(r)
        items, quota = [], {}
        for fid, v in by_f.items():
            own = int(folders[fid]["push_limit"] or 0)
            n = min(len(v), own) if own > 0 else (min(len(v), limit) if limit > 0 else len(v))
            quota[fid] = n
            items += [(r, fid) for r in v[:n]]
        items.sort(key=lambda t: key(t[0]))
        groups = {"morning": 0, "quiet": 0, "recent": 0, "older": 0, "yesterday": 0}
        yday = today - 86400
        for r, _fid in items:
            g = group(r)
            if g == 3:
                groups["yesterday" if (r["last_seen"] or 0) >= yday else "older"] += 1
            else:
                groups[("morning", "quiet", "recent")[g]] += 1
        return {"items": [(r["chat_id"], r["topic_id"], fid) for r, fid in items], "by_folder": quota,
                "pool": [(r["chat_id"], r["topic_id"], cmap[r["chat_id"]]) for r in rows],   # son chegarasisiz
                "no_account": no_account, "quiet": [], "matched": matched, "fresh": fresh, "cooled": busy,
                "repeated": repeated, "got_before": got_before, "slot": "evening" if evening else slot, "groups": groups, "limit": limit,
                "push_id": push_id}

    def delays(self) -> tuple[float, float]:
        return SPEEDS.get(self.db.get("push_speed"), SPEEDS["normal"])

    def estimate_minutes(self, n: int) -> int:
        lo, hi = self.delays()
        return max(1, round(n * (lo + hi + 1.0) / 2 / 60))

    def stop(self) -> None:
        self._stop = True
        for t in list(self._workers):
            t.cancel()

    def shutdown(self) -> None:
        """Bot to'xtayapti (yangilanish, qayta ishga tushish): Push «uzildi» deb yoziladi — bot qayta ishga tushganda
        joyidan davom etadi. ⏹ bilan to'xtatilgani esa davom etmaydi."""
        self._halt = True
        self.stop()

    async def wait_idle(self, timeout: float = 5.0) -> None:
        end = time.monotonic() + timeout
        while self.running and time.monotonic() < end:
            await asyncio.sleep(0.05)

    # ------------------------------------------------------------ yangilanishdan keyin davom ettirish
    def resume_candidate(self, started: int):
        """Bot qayta ishga tushdi: oxirgi Push yaqinda uzilgan bo'lsa — o'sha (broadcasts qatori), aks holda None."""
        b = self.db.one("SELECT * FROM broadcasts ORDER BY id DESC LIMIT 1")
        if b is None or not self.db.flag("push_enabled"):
            return None
        end = b["finished_ts"] or 0
        if b["status"] == "interrupted" and end >= started - RESUME_WINDOW:
            return b
        if b["status"] == "stopped" and self.db.get("push_resume_v") != "1" and end >= started - LEGACY_GAP:
            return b                     # eski versiya yangilanishda Push'ni «stopped» deb yozardi (bir marta)
        return None

    def continuable(self):
        """Oxirgi Push to'liq bitmagan (Telegram kuttirdi, ⏹, uzildi) va yaqinda tugagan: (qator, qolgan son)."""
        if self.running or not self.db.flag("push_enabled"):
            return None
        b = self.db.one("SELECT * FROM broadcasts ORDER BY id DESC LIMIT 1")
        if b is None or b["status"] == "running" or not b["finished_ts"] \
                or self.clock() - b["finished_ts"] > CONTINUE_HOURS * 3600:
            return None
        rem = int(b["total"] or 0) - int(b["sent"] or 0)
        return (b, rem) if rem > 0 else None

    async def continue_last(self) -> dict:
        """▶️ Davom ettirish: o'sha Push — yetmay qolgan papkalar o'z soniga yetguncha (yuborilganlarga qayta yo'q)."""
        c = self.continuable()
        if c is None:
            return {"status": "nothing"}
        b = c[0]
        return await self.run(b["trigger"] or "manual", b["slot"] or self.slot(b["started_ts"]), resume=b)

    async def resume_interrupted(self, started: int, wait: float = ACCOUNT_WAIT) -> dict | None:
        """Yangilanish Push'ni uzib qo'ygan bo'lsa — joyidan davom: yuborilganlarga qayta yubormaydi (3 soat
        qoidasi), son — o'sha (hozirgi sozlama), tartib — boshlangan paytdagi kun bo'lagi bo'yicha."""
        b = self.resume_candidate(started)
        self.db.set("push_resume_v", "1")
        if b is None:
            return None
        accs = {f["push_account_id"] for f in P.folders(self.db) if f["push_on"] and f["push_account_id"]}
        end = time.monotonic() + wait
        while time.monotonic() < end and self.pool is not None and \
                not all(self.pool.state_of(a) in ("online", "paused") for a in accs):
            await asyncio.sleep(2)                 # akkauntlar ulanguncha
        if self.running or self.db.scalar("SELECT MAX(id) FROM broadcasts") != b["id"]:
            return None                            # kutish paytida yangi Push boshlangan
        log.info("Push #%s uzilgan edi — joyidan davom etadi", b["id"])
        return await self.run(b["trigger"] or "manual", b["slot"] or self.slot(b["started_ts"]), resume=b)

    # ------------------------------------------------------------ yuborish
    async def run(self, trigger: str = "manual", slot: str | None = None, progress=None, resume=None) -> dict:
        if not self.db.flag("push_enabled"):
            return {"status": "disabled"}
        if self.running:
            return {"status": "busy"}
        push = L.get(self.db, resume["push_id"]) if resume is not None and resume["push_id"] else self.current()
        if not L.has_content(push):
            return {"status": "empty"}
        text, media = (push["text"] or "").strip(), L.media_of(push)
        control = bool(resume["control"]) if resume is not None else self.db.flag("push_control")
        self._stop = self._halt = False
        aud = self.audience(slot, push_id=push["id"])
        prev_ok: dict[int, int] = {}               # davom ettirilsa: papkada oldin yuborilgan
        failed_before: set = set()                 # … va lidning o'zi sababli yuborib bo'lmagan (qayta urinilmaydi)
        if resume is not None:
            for r in self.db.all("SELECT folder_id, COUNT(*) n FROM push_log WHERE bid=? AND held=0 GROUP BY folder_id",
                                 (resume["id"],)):
                if r["folder_id"] is not None:
                    prev_ok[r["folder_id"]] = r["n"]
            for r in self.db.all("SELECT chat_id, topic_id FROM push_fail WHERE bid=?", (resume["id"],)):
                failed_before.add((r["chat_id"], r["topic_id"]))
        pool = [x for x in aud["pool"] if (x[0], x[1]) not in failed_before]   # tartib bilan, son chegarasisiz
        queues: dict[int, deque] = {}
        for i, (chat_id, topic_id, fid) in enumerate(pool):
            queues.setdefault(fid, deque()).append((i, chat_id, topic_id))
        fids = set(queues) | set(prev_ok)
        for fid in fids:
            queues.setdefault(fid, deque())
        ok: dict[int, int] = dict(prev_ok)         # papka: yuborilgan
        busy: dict[int, int] = {}                  # papka: hozir yuborilayotgan
        short: dict[int, int] = {}                 # papka: akkaunt sababli yetmay qolgan (▶️ davom ettirsa bo'ladi)
        closed: set[int] = set()                   # navbati tugagan papkalar
        avail0 = {fid: prev_ok.get(fid, 0) + len(queues[fid]) for fid in fids}

        def cap(fid: int) -> int:
            """Papkaga hozirgi son: papkaning o'z soni, bo'lmasa umumiy; 0 — hammasi. Push paytida ham o'qiladi."""
            f = P.folder(self.db, fid)
            own = int(f["push_limit"] or 0) if f else 0
            lim = own if own > 0 else max(0, self.db.get_int("push_limit"))
            return lim if lim > 0 else avail0.get(fid, 0)

        def target(fid: int) -> int:
            """Shu papkaga nechta bo'ladi: son — lekin lid yetmasa, bori."""
            have = ok.get(fid, 0) + busy.get(fid, 0) + len(queues[fid]) + short.get(fid, 0)
            if fid in closed:
                have = ok.get(fid, 0) + short.get(fid, 0)
            return min(cap(fid), have)

        def total() -> int:
            return sum(target(fid) for fid in fids)

        if resume is not None:
            bid = int(resume["id"])
            self.db.run("UPDATE broadcasts SET status='running', finished_ts=NULL WHERE id=?", (bid,))
        else:
            bid = int(self.db.run("INSERT INTO broadcasts(started_ts, trigger, total, kind, slot, push_id, control) "
                                  "VALUES(?,?,?,?,?,?,?)",
                                  (int(self.clock()), trigger, total(), push["kind"], aud["slot"], push["id"],
                                   1 if control else 0)).lastrowid)
        stat = {"sent": sum(prev_ok.values()), "failed": 0, "done": 0, "aborted": "", "held": 0}
        reasons: dict[str, int] = {}
        per_folder: dict[int, list[int]] = {fid: [prev_ok.get(fid, 0), 0] for fid in prev_ok}

        def fail(reason: str, fid: int, c: int | None = None, t: int | None = None, lead: bool = False,
                 n: int = 1) -> None:
            """lead=True — lidning o'zi sababli (topik yopiq va h.k.): o'rniga keyingi lid; davom ettirilsa ham
            qayta urinilmaydi. Akkaunt sababli (kutish, ulanmagan, spam) — yetmagani ▶️ bilan davom ettiriladi."""
            stat["failed"] += n
            reasons[reason] = reasons.get(reason, 0) + n
            per_folder.setdefault(fid, [0, 0])[1] += n
            if lead and c is not None:
                self.db.run("INSERT INTO push_fail(bid, chat_id, topic_id, folder_id, ts) VALUES(?,?,?,?,?)",
                            (bid, c, t, fid, int(self.clock())))

        async def tick() -> None:
            stat["done"] += 1
            if stat["done"] % PROGRESS_EVERY == 0:
                n = total()
                self.db.run("UPDATE broadcasts SET sent=?, failed=?, total=? WHERE id=?",
                            (stat["sent"], stat["failed"], n, bid))
                if progress:
                    try:
                        await progress(stat["sent"], stat["failed"], n)
                    except Exception:
                        pass

        acc_of = {}
        for fid in fids:
            f = P.folder(self.db, fid)
            acc_of[fid] = f["push_account_id"] if f else 0
        groups: dict[int, list[int]] = {}          # akkaunt → uning papkalari
        for fid in fids:
            if queues[fid]:
                groups.setdefault(acc_of[fid], []).append(fid)
        names = {fid: (P.folder(self.db, fid) or {"name": "?"})["name"] for fid in fids}
        waiting: dict[int, int] = {}              # papka: Telegram aytgan kutish qachon tugaydi

        async def worker(acc_id, mine: list[int]) -> None:
            def pick() -> int | None:
                """Keyingi lid qaysi papkadan: soni to'lmagan papkalar ichida tartib bo'yicha birinchisi."""
                best = None
                for fid in mine:
                    q = queues[fid]
                    if q and ok.get(fid, 0) + busy.get(fid, 0) < cap(fid) and \
                            (best is None or q[0][0] < queues[best][0][0]):
                        best = fid
                return best

            def fail_rest(reason: str) -> None:
                """Akkaunt sababli qolgani yuborilmadi: har papkaga yetmay qolgan son (▶️ Davom ettirish mumkin)."""
                for fid in mine:
                    need = max(0, min(cap(fid), ok.get(fid, 0) + len(queues[fid])) - ok.get(fid, 0))
                    if need:
                        fail(reason, fid, n=need)
                        short[fid] = short.get(fid, 0) + need
                    queues[fid].clear()

            try:
                sender = self.pool.sender(acc_id) if self.pool is not None else None
                if sender is None or sender.state != "online":
                    fail_rest("akkaunt tarmoqda emas")
                    return
                if spam_limited(self.db, acc_id):         # @SpamBot: Telegram cheklov qo'ygan — bu akkauntdan yo'q
                    fail_rest("akkauntda spam-cheklov")
                    return
                first = True
                slow, waits, errors = 1, 0, 0             # Telegram kuttirgandan keyin — sekinroq
                while not self._stop:
                    fid = pick()                          # son pauza paytida o'zgargan bo'lishi mumkin
                    if fid is None:
                        return
                    idx, chat_id, topic_id = queues[fid].popleft()
                    if control and held_out(bid, chat_id, topic_id):
                        now = int(self.clock())           # 🧪 nazorat guruhi: yuborilmaydi, o'rniga keyingisi
                        self.db.run("INSERT OR IGNORE INTO push_log(bid, chat_id, topic_id, folder_id, ts, held) "
                                    "VALUES(?,?,?,?,?,1)", (bid, chat_id, topic_id, fid, now))
                        self.db.run("INSERT OR IGNORE INTO push_got(push_id, chat_id, topic_id, ts, bid, held) "
                                    "VALUES(?,?,?,?,?,1)", (push["id"], chat_id, topic_id, now, bid))
                        stat["held"] += 1
                        continue
                    if not first:
                        await self._sleep(random.uniform(*self.delays()) * slow)
                        if self._stop:
                            queues[fid].appendleft((idx, chat_id, topic_id))
                            return
                        if ok.get(fid, 0) + busy.get(fid, 0) >= cap(fid):   # son kutish paytida kamaytirilgan
                            queues[fid].appendleft((idx, chat_id, topic_id))
                            continue
                    first = False
                    busy[fid] = busy.get(fid, 0) + 1
                    try:
                        async def send_and_mark(c=chat_id, t=topic_id, f_id=fid):
                            _SENDING[(int(c), int(t))] = time.monotonic()
                            try:
                                ids = await (sender.send_media(c, t, media, text) if media else
                                             sender.send_text(c, t, text))
                                ids = ids if isinstance(ids, list) else [ids]
                                now = int(self.clock())
                                for mid in ids:
                                    self.db.run("INSERT OR IGNORE INTO ignored_msgs(chat_id, msg_id, ts) VALUES(?,?,?)",
                                                (c, int(mid), now))
                            finally:
                                _SENDING.pop((int(c), int(t)), None)
                            self.db.run("UPDATE threads SET last_push_ts=? WHERE chat_id=? AND topic_id=?",
                                        (now, c, t))
                            self.db.run("INSERT OR IGNORE INTO push_log(bid, chat_id, topic_id, folder_id, ts) "
                                        "VALUES(?,?,?,?,?)", (bid, c, t, f_id, now))
                            self.db.run("INSERT OR REPLACE INTO push_got(push_id, chat_id, topic_id, ts, bid, held) "
                                        "VALUES(?,?,?,?,?,0)", (push["id"], c, t, now, bid))

                        job = asyncio.ensure_future(send_and_mark())
                        job.add_done_callback(lambda f: f.cancelled() or f.exception())
                        await asyncio.shield(job)
                        stat["sent"] += 1
                        ok[fid] = ok.get(fid, 0) + 1
                        per_folder.setdefault(fid, [0, 0])[0] += 1
                        errors = 0
                    except SendSkip as exc:               # lidning o'zi sababli — o'rniga keyingi lid
                        fail(str(exc)[:60] or "skip", fid, chat_id, topic_id, lead=True)
                    except SendWait as exc:                # Telegram: «N soniya kuting» — papka kutadi, boshqalar davom
                        sec = max(1, int(exc.seconds))
                        until = int(self.clock()) + sec + 5
                        if sec <= MAX_WAIT and waits < MAX_WAITS:
                            waits += 1
                            queues[fid].appendleft((idx, chat_id, topic_id))     # shu lid — kutishdan keyin
                            for f2 in mine:
                                waiting[f2] = until
                            log.info("Push: akkaunt %s — Telegram %s s kutishni so'radi", acc_id, sec)
                            busy[fid] -= 1
                            try:
                                await self._sleep(sec + 5)
                            finally:
                                for f2 in mine:
                                    waiting.pop(f2, None)
                            slow = min(slow * 2, 4)
                            first = True                  # kutishdan keyin darhol davom
                            continue
                        stat["aborted"] = str(exc)
                        why = (f"Telegram {(sec + 59) // 60} daq kutishni so'radi "
                               f"({datetime.fromtimestamp(until, self.tz):%H:%M} gacha) — keyin ▶️ Davom ettirish")
                        queues[fid].appendleft((idx, chat_id, topic_id))
                        busy[fid] -= 1
                        fail_rest(why)
                        await tick()
                        return
                    except SendAbort as exc:
                        stat["aborted"] = str(exc)
                        queues[fid].appendleft((idx, chat_id, topic_id))
                        busy[fid] -= 1
                        fail_rest(f"to'xtatildi: {str(exc)[:50]}")
                        await tick()
                        return
                    except Exception as exc:
                        errors += 1
                        fail(f"{type(exc).__name__}", fid, chat_id, topic_id)
                        log.warning("Push xatosi %s/%s: %s", chat_id, topic_id, type(exc).__name__)
                        if errors >= MAX_ERRORS:          # bir xil xato qaytaveryapti — akkaunt to'xtaydi
                            busy[fid] -= 1
                            fail_rest(f"{type(exc).__name__}")
                            await tick()
                            return
                    busy[fid] = max(0, busy.get(fid, 0) - 1)
                    await tick()
            finally:
                if not self._stop:
                    closed.update(mine)

        status = "done"
        n = 0
        self.running = True

        def live() -> str:
            out = f"{stat['sent']}/{total()}" + (f" · ✖️ {stat['failed']}" if stat["failed"] else "")
            if waiting:                                 # «⏳ RD 9 → 12:44» — Telegram kuttiryapti, keyin o'zi davom etadi
                out += " · ⏳ " + ", ".join(f"{names.get(f, '?')} → {datetime.fromtimestamp(u, self.tz):%H:%M}"
                                            for f, u in sorted(waiting.items()))
            return out
        self._live = live
        order = {f["id"]: i for i, f in enumerate(P.folders(self.db))}

        def snap() -> dict:
            """«Проёб»dagi Push paneli uchun: har RD — nechta ketdi / nechtadan, kutyaptimi."""
            rows = []
            for fid in sorted(fids, key=lambda f: order.get(f, 10 ** 6)):
                rows.append({"fid": fid, "name": names.get(fid, "?"), "sent": ok.get(fid, 0), "total": target(fid),
                             "wait": waiting.get(fid)})
            return {"rows": rows, "sent": stat["sent"], "total": total()}

        gp = None                                  # 📣 «Проёб»da hamma ko'radigan Push paneli
        if self.db.flag("push_group") and self.db.get("proyob_group_id") and \
                getattr(self.notifier, "bot", None) is not None:
            from .push_group import GroupPanel
            gp = GroupPanel(self, bid, text, media)
            try:
                await gp.start(snap())
            except Exception as exc:
                log.info("Push paneli guruhga yozilmadi: %s", exc)
                gp = None
        updater = asyncio.create_task(gp.loop(snap)) if gp is not None else None
        try:
            self._workers = [asyncio.create_task(worker(k, v)) for k, v in groups.items()]
            results = await asyncio.gather(*self._workers, return_exceptions=True)
            for res in results:
                if isinstance(res, asyncio.CancelledError) and not self._stop:
                    raise res
            if self._halt:
                status = "interrupted"                    # yangilanish — keyin joyidan davom etadi
            elif self._stop:
                status = "stopped"
            elif stat["aborted"] and not stat["sent"]:
                status = "aborted"
        except asyncio.CancelledError:
            status = "interrupted"
            raise
        finally:
            if updater is not None:
                updater.cancel()
            n = total()
            self.db.run("UPDATE broadcasts SET sent=?, failed=?, status=?, finished_ts=?, total=? WHERE id=?",
                        (stat["sent"], stat["failed"], status, int(self.clock()), n, bid))
            self.running = False
            self._workers = []
            self.progress_text = ""
        res = {"status": status, "sent": stat["sent"], "failed": stat["failed"], "total": n, "held": stat["held"],
               "reasons": reasons, "reason": stat["aborted"], "per_folder": per_folder, "aud": aud,
               "push_id": push["id"]}
        self.last_report = (int(self.clock()), res)
        if gp is not None and status != "interrupted":   # uzilgan (yangilanish) — davom etganda o'sha panel
            try:
                await gp.finish(snap(), status)
            except Exception as exc:
                log.info("Push paneli yakunlanmadi: %s", exc)
        return res

    async def send_test(self, bot, uid: int) -> None:
        """Sinov: faqat adminning o'ziga (bot orqali), mijoz ko'radigandek."""
        cur = self.current()
        text, media = ((cur["text"] or "").strip() if cur else ""), self.media()
        if not text and not media:
            raise ValueError("empty")
        if media:
            kind = media["kind"]
            src = media.get("file_id")
            path = media.get("path") or ""
            if path and os.path.exists(path):           # fayl o'zimizda — bot tokeni almashsa ham ishlaydi
                from aiogram.types import FSInputFile
                src = FSInputFile(path)
            method = {"voice": bot.send_voice, "video": bot.send_video, "video_note": bot.send_video_note,
                      "photo": bot.send_photo, "audio": bot.send_audio, "animation": bot.send_animation}.get(
                kind, bot.send_document)
            if kind == "video_note":
                if text:
                    await bot.send_message(uid, text)
                await method(uid, src)
            else:
                await method(uid, src, caption=text or None)
        else:
            await bot.send_message(uid, text)

    # ------------------------------------------------------------ jadval (o'chirilgan: Push faqat qo'lda)
    async def tick_schedule(self, now: int | None = None) -> dict | None:
        return None
