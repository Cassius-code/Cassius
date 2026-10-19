"""Push: issiq lidlarga xabar — har papka o'z Push akkauntidan. Qo'lda (tugma) va jadval bo'yicha (avtomat).

Eski botda ishlagan qoidalar saqlangan: soni HAR papkaga; ⚡/💊 yo'q; stavkasi tugamagan yangi lidga yo'q;
yaqinda yozishganlarga yo'q; 3 soat ichida qayta yo'q; tinch vaqt; tartib: bugun → kecha → hafta → eski.
"""
from __future__ import annotations

import asyncio
import os
import json
import logging
import random
import time
from datetime import datetime, time as dtime, timedelta
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


def _hm(raw: str) -> int | None:
    try:
        t = parse_hhmm(raw)
        return t.hour * 60 + t.minute
    except (ValueError, TypeError):
        return None


def in_quiet(frm: str, to: str, minute: int) -> bool:
    a, b = _hm(frm or ""), _hm(to or "")
    if a is None or b is None or a == b:
        return False
    return a <= minute < b if a < b else (minute >= a or minute < b)


def push_times(db: Database) -> list[str]:
    out = []
    for part in (db.get("push_times") or "").replace(";", ",").replace(" ", ",").split(","):
        if _hm(part) is not None:
            t = parse_hhmm(part)
            out.append(f"{t.hour:02d}:{t.minute:02d}")
    return sorted(set(out))


def slot_of(db: Database, minute: int) -> str:
    """Jadvaldagi 1-vaqt — 'all' (ertalab), oxirgisi — 'evening', o'rtadagilar — 'day'."""
    times = [_hm(t) for t in push_times(db)]
    if not times:
        return "all"
    idx = max([i for i, t in enumerate(times) if t <= minute] or [0])
    if idx == 0:
        return "all"
    return "evening" if idx == len(times) - 1 and len(times) >= 3 else "day"


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

    def _period(self) -> tuple[int, int]:
        lo = 0
        try:
            raw = self.db.get("push_from") or self.db.get("track_from")
            if raw:
                lo = int(datetime.combine(parse_date(raw), dtime(0, 0), tzinfo=self.tz).timestamp())
        except ValueError:
            lo = 0
        hi = 2 ** 31
        if self.db.get("push_to"):
            try:
                hi = int(datetime.combine(parse_date(self.db.get("push_to")) + timedelta(days=1), dtime(0, 0),
                                          tzinfo=self.tz).timestamp()) - 1
            except ValueError:
                pass
        return lo, hi

    def _push_emojis(self) -> list[str]:
        return [ch for ch in self.db.get("push_emojis") if not ch.isspace() and ch not in ",;️‍"]

    # ------------------------------------------------------------ kimga
    def audience(self, slot: str = "all", now: int | None = None) -> dict:
        now = int(self.clock() if now is None else now)
        lo, hi = self._period()
        cmap = P.chat_folder_map(self.db)
        folders = {f["id"]: f for f in P.folders(self.db)}
        allowed = {fid for fid, f in folders.items() if f["push_on"]}
        t_local = datetime.fromtimestamp(now, self.tz)
        mod = t_local.hour * 60 + t_local.minute
        quiet = []
        for fid in sorted(allowed):
            f = folders[fid]
            frm, to = (f["quiet_from"], f["quiet_to"]) if f["quiet_from"] and f["quiet_to"] else (
                self.db.get("push_quiet_from"), self.db.get("push_quiet_to"))
            if in_quiet(frm, to, mod):
                quiet.append(fid)
        allowed -= set(quiet)
        no_account = sorted(fid for fid in allowed if not folders[fid]["push_account_id"])
        allowed -= set(no_account)
        skip, push_e = skip_list(self.db), self._push_emojis()
        rows = self.db.all(
            "SELECT th.*, CASE WHEN th.topic_id<>0 THEN TRIM(COALESCE(t.icon,'') || ' ' || COALESCE(t.title,'')) "
            "ELSE COALESCE(c.title,'') END AS label FROM threads th JOIN chats c ON c.chat_id=th.chat_id "
            "LEFT JOIN topics t ON t.chat_id=th.chat_id AND t.topic_id=th.topic_id "
            "WHERE th.first_seen IS NOT NULL AND th.first_seen BETWEEN ? AND ?", (lo, hi))
        rows = [r for r in rows if cmap.get(r["chat_id"]) in allowed and not label_excluded(r["label"], skip)
                and (not push_e or label_excluded(r["label"], push_e))]
        matched = len(rows)
        fresh_n = max(0, self.db.get_int("push_newlead_minutes"))
        border = now - fresh_n * 60
        kept = [r for r in rows if r["stavka"] != "on" and (not fresh_n or r["first_seen"] <= border)]
        fresh, rows = len(rows) - len(kept), kept
        idle = max(0, self.db.get_int("push_idle_minutes"))
        cooled = 0
        if idle:
            kept = [r for r in rows if max(r["last_seen"] or 0, r["last_activity"] or 0) <= now - idle * 60]
            cooled, rows = len(rows) - len(kept), kept
        repeat = max(MIN_REPEAT, self.db.get_int("push_repeat_minutes"))
        kept = [r for r in rows if not r["last_push_ts"] or r["last_push_ts"] <= now - repeat * 60]
        repeated, rows = len(rows) - len(kept), kept
        today = day_start(now, self.tz)
        yesterday, week_ago = today - 86400, today - 8 * 86400

        def active_today(r) -> bool:
            return max(r["last_seen"] or 0, r["last_activity"] or 0) >= today

        slot_skipped = 0
        if slot == "evening":
            kept = [r for r in rows if active_today(r)]
            slot_skipped, rows = len(rows) - len(kept), kept

        def bucket(r) -> int:
            t = r["first_seen"]
            return 0 if t >= today else 1 if t >= yesterday else 2 if t >= week_ago else 3

        def key(r):
            base = (bucket(r), r["last_push_ts"] is not None, r["last_push_ts"] or 0, -(r["last_seen"] or 0))
            return ((0 if active_today(r) else 1),) + base if slot == "day" else base

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
        return {"items": [(r["chat_id"], r["topic_id"], fid) for r, fid in items], "by_folder": quota,
                "no_account": no_account, "quiet": quiet, "matched": matched, "fresh": fresh, "cooled": cooled,
                "repeated": repeated, "slot_skipped": slot_skipped, "limit": limit}

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
    async def run(self, trigger: str = "manual", slot: str = "all", progress=None) -> dict:
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

    # ------------------------------------------------------------ jadval
    async def tick_schedule(self, now: int | None = None) -> dict | None:
        """Avtomat Push: belgilangan vaqt kelganda (bir marta). Natija egasiga yuboriladi."""
        if not self.db.flag("push_auto") or not self.db.flag("bot_enabled") or self.running:
            return None
        now = int(self.clock() if now is None else now)
        t = datetime.fromtimestamp(now, self.tz)
        mod = t.hour * 60 + t.minute
        for hm in push_times(self.db):
            m = _hm(hm)
            key = f"{t.date().isoformat()} {hm}"
            if m <= mod < m + 30 and self.db.get("push_auto_last") < key:
                self.db.set("push_auto_last", key)
                if not self.has_content():
                    await self.notifier.notify_owner("⚠️ Avtomat Push: matn yo'q — yuborilmadi.", key="auto-empty",
                                                     min_interval=3600)
                    return None
                res = await self.run("auto", slot_of(self.db, m))
                return res
        return None
