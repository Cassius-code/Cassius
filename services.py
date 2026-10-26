"""Fon ishlari: har 10 soniyada nazorat (zaderjka, stavka, ishga kelish, tanaffus, avtomat Push), kunlik hisobot
egaga, haftalik xulosa «Проёб»ga, haftalik zaxira nusxa, eski yozuvlarni tozalash."""
from __future__ import annotations

import asyncio
import datetime as dt
import gzip
import logging
import os
import sqlite3
import time

from . import kassa as K
from .reports import summary, weekly_group
from .timeutil import local_date, parse_hhmm

log = logging.getLogger("services")

TICK = 10                      # hisobot, zaxira, Push jadvali va h.k.
FAST_TICK = 2                  # zaderjka va stavka — har 2 soniyada
JOURNAL_DAYS = 14


def first_run(db, now: int, tz) -> None:
    """Birinchi ishga tushish: zaderjka va lid hisobi SHU paytdan (eski tarix uchun signal yog'ilmasin)."""
    if not db.get_int("delay_from"):
        db.set("delay_from", str(now))
    if not db.get("track_from"):
        db.set("track_from", local_date(now, tz).isoformat())
    if not db.get_int("backup_last"):
        db.set("backup_last", str(now))
    old_rate = db.one("SELECT value FROM settings WHERE key='late_fine_per_min'")
    if old_rate is not None and not db.get("late_fine") and old_rate["value"] not in ("", "0"):
        db.set("late_fine", old_rate["value"])
    K.seed_prices(db)
    K.seed_opening(db)
    if not db.get_int("cards_since"):
        db.set("cards_since", str(now))                  # karta, Push natijasi, faollik — shu paytdan yig'iladi
    if not db.get("greet_migrated"):                     # eski yozuvlar: kelgan = «доброе утро» yozgan
        db.run("UPDATE attendance SET greet_ts=arrived_ts WHERE greet_ts IS NULL AND arrived_ts IS NOT NULL")
        db.set("greet_migrated", "1")
    if not db.get("stavka_fix_v1"):
        # eski versiyada «🔒 Qattiq rejim» tugmasi aslida stavkani o'chirib-yoqardi (ikki tugmaga bitta nom) —
        # stavka bilmasdan o'chirilgan bo'lishi mumkin: bir marta qayta yoqiladi
        if db.get("stavka_enabled") == "0":
            db.set("stavka_enabled", "1")
            log.info("Stavka qayta yoqildi (eski «Qattiq rejim» tugmasi uni o'chirgan edi)")
        db.set("stavka_fix_v1", "1")
    if not db.get("pay_remind_v1"):                      # 💳 eski kartalar uchun eslatma ketmaydi (faqat yangilari)
        db.run("UPDATE cards SET reminded=1")
        db.set("pay_remind_v1", "1")


def make_backup(ctx) -> tuple[bytes, str]:
    """Butun bazaning izchil nusxasi (ish to'xtamaydi). 45 MB dan katta bo'lsa — gzip."""
    tmp = os.path.join(str(ctx.cfg.data_dir), f".backup_{int(time.time())}.sqlite3")
    src = ctx.db.conn
    dst = sqlite3.connect(tmp)
    try:
        with ctx.db._lock:
            src.backup(dst)
    finally:
        dst.close()
    try:
        with open(tmp, "rb") as f:
            data = f.read()
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    stamp = dt.datetime.now(ctx.tz).strftime("%Y-%m-%d_%H%M")
    name = f"rdbot_{stamp}.sqlite3"
    if len(data) > 45 * 1024 * 1024:
        data, name = gzip.compress(data), name + ".gz"
    return data, name


class Scheduler:
    def __init__(self, ctx):
        self.ctx = ctx
        self._push_task: asyncio.Task | None = None
        self._spam_task: asyncio.Task | None = None
        self._last_cool = 0.0
        self._last_nudge = 0.0
        self._last_prune = 0.0
        self._last_pool = 0.0
        self._last_board = 0.0

    async def run(self) -> None:
        last_full = 0.0
        while True:
            started = time.monotonic()
            if started - last_full >= TICK:
                last_full = started
                await self.step()
            else:
                await self._safe("zaderjka va stavka", self.ctx.tracker.tick(int(self.ctx.clock())))
            if time.monotonic() - self._last_board >= 5:          # 📌 «Проёб»dagi doska — son o'zgarsa
                self._last_board = time.monotonic()
                from . import board
                await self._safe("doska", board.refresh(self.ctx, int(self.ctx.clock())))
            await asyncio.sleep(max(0.5, FAST_TICK - (time.monotonic() - started)))

    async def _safe(self, name: str, coro) -> None:
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Fon ishi xatosi: %s", name)

    async def step(self, now: int | None = None) -> None:
        ctx = self.ctx
        now = int(ctx.clock() if now is None else now)
        await self._safe("zaderjka va stavka", ctx.tracker.tick(now))
        await self._safe("ishga kelish va tanaffus", ctx.att.tick(now))
        if ctx.pusher is not None and (self._push_task is None or self._push_task.done()):
            self._push_task = asyncio.create_task(self._safe("avtomat Push", self._auto_push(now)))
        if self._spam_task is None or self._spam_task.done():   # 🛡 @SpamBot — fonda (bir necha soniya oladi)
            from . import guard
            self._spam_task = asyncio.create_task(self._safe("@SpamBot", guard.daily(ctx, now)))
        from . import push_group, tidy
        await self._safe("Push paneli", push_group.cleanup(ctx, now))     # tugaganiga 5 daqiqa — panel o'chadi
        await self._safe("«Проёб»ni tozalash", tidy.sweep(ctx, now))      # 🧹 vaqti kelgan bot xabarlari o'chadi
        if time.monotonic() - self._last_cool >= 120:              # 📉 soviyotgan lidlar — har 2 daqiqada
            self._last_cool = time.monotonic()
            from . import insights
            await self._safe("soviyotgan lidlar", insights.cooling_alerts(ctx, now))
        if time.monotonic() - self._last_nudge >= 60:              # 🆕 jim yangi lid · 💳 to'lov — har daqiqada
            self._last_nudge = time.monotonic()
            from . import insights
            await self._safe("yangi lid jim", insights.newlead_alerts(ctx, now))
            await self._safe("to'lov eslatmasi", insights.pay_alerts(ctx, now))
        await self._safe("kunlik hisobot", self.daily_report(now))
        await self._safe("haftalik xulosa", self.weekly(now))
        await self._safe("zaxira nusxa", self.backup(now))
        if time.monotonic() - self._last_pool > 60 and ctx.pool is not None:
            self._last_pool = time.monotonic()
            try:
                ctx.pool.sync()
            except Exception:
                log.exception("Push akkauntlar")
        if time.time() - self._last_prune > 3600:
            self._last_prune = time.time()
            try:
                self.prune(now)
            except Exception:
                log.exception("Tozalash")

    async def _auto_push(self, now: int) -> None:
        res = await self.ctx.pusher.tick_schedule(now)
        if res:
            from .panel_push import report_text
            from .ui import Req
            try:
                req = Req(uid=0, chat_id=0, level="owner", lang=self.ctx.lang())
                text = report_text(self.ctx, req, res)
            except Exception:
                text = f"📣 Avtomat Push: {res.get('sent', 0)} / {res.get('total', 0)}"
            await self.ctx.notifier.notify_owner(text)

    # ------------------------------------------------------------ kunlik hisobot (egaga)
    async def daily_report(self, now: int) -> None:
        db, ctx = self.ctx.db, self.ctx
        if not db.flag("report_enabled") or not db.flag("bot_enabled"):
            return
        t = dt.datetime.fromtimestamp(now, ctx.tz)
        try:
            at = parse_hhmm(db.get("report_time"))
        except ValueError:
            return
        day = t.date().isoformat()
        if t.time() < at or db.get("report_last") >= day:
            return
        db.set("report_last", day)
        owners = ctx.notifier.owner_ids()
        d = t.date()
        await ctx.notifier._send_many(owners, lambda: (summary(ctx, d, d, ctx.lang(), owner=True), None))
        others = [u for u in ctx.notifier.staff_ids() if u not in owners]
        if others:
            await ctx.notifier._send_many(others, lambda: (summary(ctx, d, d, ctx.lang(), owner=False), None))

    # ------------------------------------------------------------ haftalik xulosa («Проёб», ruscha, pulsiz)
    async def weekly(self, now: int) -> None:
        db, ctx = self.ctx.db, self.ctx
        if not db.flag("weekly_enabled") or not db.flag("bot_enabled") or not db.get("proyob_group_id"):
            return
        t = dt.datetime.fromtimestamp(now, ctx.tz)
        if t.weekday() != 6 or t.hour < 21:
            return
        mon = K.week_start(t.date())
        key = mon.isoformat()
        if db.get("weekly_last") >= key:
            return
        db.set("weekly_last", key)
        await ctx.notifier.send_group(weekly_group(ctx, mon, t.date()))

    # ------------------------------------------------------------ zaxira nusxa (haftada bir, egaga)
    async def backup(self, now: int) -> None:
        db, ctx = self.ctx.db, self.ctx
        if now - db.get_int("backup_last") < 7 * 86400:
            return
        db.set("backup_last", str(now))
        data, name = await asyncio.to_thread(make_backup, ctx)
        ru = ctx.lang(ctx.cfg.main_owner) == "ru"
        cap = ("💾 Еженедельная копия базы. Храните — из неё можно всё восстановить." if ru else
               "💾 Haftalik baza nusxasi. Saqlab qo'ying — undan hammasini tiklash mumkin.")
        try:
            await ctx.notifier.send_document(ctx.cfg.main_owner, data, name, cap)
        except Exception:
            log.exception("Zaxira yuborilmadi")

    # ------------------------------------------------------------ tozalash
    def prune(self, now: int) -> None:
        db = self.ctx.db
        db.run("DELETE FROM journal WHERE at<?", (now - JOURNAL_DAYS * 86400,))
        db.run("DELETE FROM ignored_msgs WHERE ts<?", (now - 14 * 86400,))
        db.run("DELETE FROM bets WHERE ts<?", (now - 30 * 86400,))
        db.run("DELETE FROM requests WHERE ts<? AND status<>'open'", (now - 30 * 86400,))
        db.run("DELETE FROM breaks WHERE start_ts<?", (now - 90 * 86400,))
        db.run("DELETE FROM pauses WHERE start_ts<? AND end_ts IS NOT NULL", (now - 90 * 86400,))
