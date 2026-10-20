"""Push: issiq lidlarga xabar — har papka o'z Push akkauntidan, faqat qo'lda (🚀 tugma).

Kimga va qaysi tartibda — soatga qarab (egasi bilan kelishilgan):
* 🌅 Ertalab (kunduzgi vaqtgacha): bugun gaplashmaganlar — kecha yozganlardan boshlab eskiroqlariga.
* ☀️ Kunduzi: faqat bugun gaplashganlar — 1) ertalab gaplashganlar, 2) belgilangan vaqtdan (30 daq / 1 soat)
  beri jim turganlar. Hozir gaplashayotganlarga (shu vaqt ichida yozishganlarga) — YO'Q.
* 🌙 Kechqurun: avval bugun gaplashganlar (kunduzgi tartibda), ular tugasa — kechagi, keyin eskiroqlar.
Baza: faqat belgilangan sanadan (28.08.2026) beri o'zi yozgan lidlar; davr — oxirgi N kun yoki sana oralig'i
(lidlar haftalar o'tib eskiradi). «Gaplashdi» — mijoz yoki xodim yozgan
(Push xabarlari hisobga kirmaydi). Har papkaga son chegarasi; ⚡/💊 yo'q; stavkasi tugamagan yangi lidga yo'q;
3 soat ichida qayta yo'q.
"""
from __future__ import annotations

import asyncio
import os
import json
import logging
import random
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from . import people as P
from .db import Database
from .rules import label_excluded, skip_list
from .tgsend import SendAbort, SendSkip
from .timeutil import day_start, parse_date, parse_hhmm

log = logging.getLogger("push")

MIN_REPEAT = 180
SPEEDS = {"fast": (1.0, 2.0), "normal": (2.0, 3.0), "slow": (3.0, 5.0)}
PROGRESS_EVERY = 5
SLOTS = ("morning", "day", "evening")


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
        self._workers: list = []
        self.progress_text = ""

    # ------------------------------------------------------------ mazmun
    def media(self) -> dict | None:
        raw = self.db.get("push_media")
        try:
            m = json.loads(raw) if raw else None
        except ValueError:
            return None
        return m if isinstance(m, dict) and m.get("kind") else None

    def has_content(self) -> bool:
        return bool(self.db.get("push_text").strip() or self.media())

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
        now = int(self.clock() if now is None else now)
        t = datetime.fromtimestamp(now, self.tz)
        return slot_at(self.db, t.hour * 60 + t.minute)

    def _push_emojis(self) -> list[str]:
        return [ch for ch in self.db.get("push_emojis") if not ch.isspace() and ch not in ",;️‍"]

    # ------------------------------------------------------------ kimga
    def audience(self, slot: str | None = None, now: int | None = None) -> dict:
        now = int(self.clock() if now is None else now)
        slot = slot if slot in SLOTS else self.slot(now)
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
        repeat = max(MIN_REPEAT, self.db.get_int("push_repeat_minutes"))
        kept = [r for r in rows if not r["last_push_ts"] or r["last_push_ts"] <= now - repeat * 60]
        repeated, rows = len(rows) - len(kept), kept

        today = day_start(now, self.tz)
        m_end, _e = slot_bounds(self.db)
        morning_end = today + m_end * 60
        idle = max(0, self.db.get_int("push_idle_minutes"))
        quiet_border = now - idle * 60

        def talk(r) -> int:                                 # oxirgi suhbat: mijoz yoki xodim (Push emas)
            return max(r["last_seen"] or 0, r["last_staff_ts"] or 0)

        morning_talk = {(x["chat_id"], x["topic_id"]) for x in self.db.all(
            "SELECT DISTINCT chat_id, topic_id FROM journal WHERE ts BETWEEN ? AND ? AND who IN ('client','staff')",
            (today, min(morning_end, now)))}

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
            rows = [r for r in rows if group(r) == 3]
            key = (lambda r: (-(r["last_seen"] or 0),))
        elif slot == "day":
            rows = [r for r in rows if group(r) < 3]
            key = (lambda r: (group(r), talk(r)))
        else:
            key = (lambda r: (group(r), talk(r) if group(r) < 3 else -(r["last_seen"] or 0)))
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
                "no_account": no_account, "quiet": [], "matched": matched, "fresh": fresh, "cooled": busy,
                "repeated": repeated, "slot": slot, "groups": groups, "limit": limit}

    def delays(self) -> tuple[float, float]:
        return SPEEDS.get(self.db.get("push_speed"), SPEEDS["normal"])

    def estimate_minutes(self, n: int) -> int:
        lo, hi = self.delays()
        return max(1, round(n * (lo + hi + 1.0) / 2 / 60))

    def stop(self) -> None:
        self._stop = True
        for t in list(self._workers):
            t.cancel()

    # ------------------------------------------------------------ yuborish
    async def run(self, trigger: str = "manual", slot: str | None = None, progress=None) -> dict:
        if not self.db.flag("push_enabled"):
            return {"status": "disabled"}
        if self.running:
            return {"status": "busy"}
        text, media = self.db.get("push_text").strip(), self.media()
        if not text and not media:
            return {"status": "empty"}
        self._stop = False
        aud = self.audience(slot)
        items = aud["items"]
        bid = int(self.db.run("INSERT INTO broadcasts(started_ts, trigger, total) VALUES(?,?,?)",
                              (int(self.clock()), trigger, len(items))).lastrowid)
        stat = {"sent": 0, "failed": 0, "done": 0, "aborted": ""}
        reasons: dict[str, int] = {}
        per_folder: dict[int, list[int]] = {}

        def fail(reason: str, fid: int) -> None:
            stat["failed"] += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            per_folder.setdefault(fid, [0, 0])[1] += 1

        async def tick() -> None:
            stat["done"] += 1
            if stat["done"] % PROGRESS_EVERY == 0:
                self.db.run("UPDATE broadcasts SET sent=?, failed=? WHERE id=?", (stat["sent"], stat["failed"], bid))
                if progress:
                    try:
                        await progress(stat["sent"], stat["failed"], len(items))
                    except Exception:
                        pass

        groups: dict[int, list] = {}
        for chat_id, topic_id, fid in items:
            f = P.folder(self.db, fid)
            groups.setdefault(f["push_account_id"] if f else 0, []).append((chat_id, topic_id, fid))

        async def worker(acc_id, group) -> None:
            sender = self.pool.sender(acc_id) if self.pool is not None else None
            if sender is None or sender.state != "online":
                for _c, _t, fid in group:
                    fail("akkaunt tarmoqda emas", fid)
                    await tick()
                return
            for i, (chat_id, topic_id, fid) in enumerate(group):
                if self._stop:
                    return
                try:
                    async def send_and_mark(c=chat_id, t=topic_id):
                        ids = await (sender.send_media(c, t, media, text) if media else
                                     sender.send_text(c, t, text))
                        ids = ids if isinstance(ids, list) else [ids]
                        now = int(self.clock())
                        for mid in ids:
                            self.db.run("INSERT OR IGNORE INTO ignored_msgs(chat_id, msg_id, ts) VALUES(?,?,?)",
                                        (c, int(mid), now))
                        self.db.run("UPDATE threads SET last_push_ts=? WHERE chat_id=? AND topic_id=?", (now, c, t))

                    job = asyncio.ensure_future(send_and_mark())
                    job.add_done_callback(lambda f: f.cancelled() or f.exception())
                    await asyncio.shield(job)
                    stat["sent"] += 1
                    per_folder.setdefault(fid, [0, 0])[0] += 1
                except SendSkip as exc:
                    fail(str(exc)[:60] or "skip", fid)
                except SendAbort as exc:
                    stat["aborted"] = str(exc)
                    for _c, _t, f2 in group[i:]:
                        fail(f"to'xtatildi: {str(exc)[:50]}", f2)
                        await tick()
                    return
                except Exception as exc:
                    fail(f"{type(exc).__name__}", fid)
                    log.warning("Push xatosi %s/%s: %s", chat_id, topic_id, type(exc).__name__)
                await tick()
                if i + 1 < len(group):
                    await self._sleep(random.uniform(*self.delays()))

        status = "done"
        self.running = True
        try:
            self._workers = [asyncio.create_task(worker(k, g)) for k, g in groups.items()]
            results = await asyncio.gather(*self._workers, return_exceptions=True)
            for res in results:
                if isinstance(res, asyncio.CancelledError) and not self._stop:
                    raise res
            if self._stop:
                status = "stopped"
            elif stat["aborted"] and not stat["sent"]:
                status = "aborted"
        except asyncio.CancelledError:
            status = "interrupted"
            raise
        finally:
            self.db.run("UPDATE broadcasts SET sent=?, failed=?, status=?, finished_ts=? WHERE id=?",
                        (stat["sent"], stat["failed"], status, int(self.clock()), bid))
            self.running = False
            self._workers = []
        return {"status": status, "sent": stat["sent"], "failed": stat["failed"], "total": len(items),
                "reasons": reasons, "reason": stat["aborted"], "per_folder": per_folder, "aud": aud}

    async def send_test(self, bot, uid: int) -> None:
        """Sinov: faqat adminning o'ziga (bot orqali), mijoz ko'radigandek."""
        text, media = self.db.get("push_text").strip(), self.media()
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
