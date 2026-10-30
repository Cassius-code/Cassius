"""Zaderjka va stavka qoidalari — botning yuragi. Telegram'ga bog'liq emas, alohida sinaladi.

Qoidalar (egasi bilan kelishilgan):
* Mijoz xabarlari FAQAT vositachi bot orqali keladi: bot (User.bot) yozgan = mijoz; har qanday odam yozgan = javob.
  Push akkauntlarimiz xabarlari hisobga olinmaydi.
* Yangi lid (yangi topik) → stavka. Stavka = N ta dumaloq video, HAR video bilan vositachi bot darrov matn ham yozadi
  (2026-10-19 jurnalida topilgan xato: 3-videodan keyingi matn mijoz xabari deb olingan edi). Stavka N-video va uning
  matni bilan tugaydi. Stavka paytida hech kimning xabari zaderjka hisoblanmaydi.
* Video belgilangan vaqtda kelmasa — «Проёб»ga «ставка» eslatmasi (zaderjka emas), ko'pi bilan K marta. K-eslatmadan
  keyin ham video kelmasa — stavka tugaydi, keyingi mijoz xabarlari oddiy zaderjka (egasi, 2026-10-26; vaqt chegarasi yo'q).
* Zaderjka: mijozning BIRINCHI javobsiz xabaridan, faqat ish vaqtida (va papkaning hamma xodimi tanaffusda bo'lmasa),
  limitdan oshsa «Проёб»ga bir marta «задержка», 15 daqiqadan keyin eslatma. Javob kelganda ✅. Jarimalar —
  💸 jadvaldagi aniq summalar (eslatmadan keyin ham javobsiz / ko'p lid birdaniga).
* Hamma xabarlar nit ichida id tartibida bir marta ishlanadi (jonli va qayta ulanishdagi xabarlar bitta yo'ldan).
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from . import people as P
from . import roster as R
from .db import Database
from .links import message_link
from .gtext import esc, head, link, small, tag
from .timeutil import minutes_up, parse_hhmm, work_seconds, local_date, is_work_time

log = logging.getLogger("rules")

MAX_LINKS = 10                 # bitta «задержка» xabarida eng ko'pi bilan nechta havola
BATCH_SEC = 40                 # yaqin zaderjkalar shuncha soniya kutib, bitta xabar bo'lib ketadi
BATCH_LOOK = 10                # 40 s dan keyin: yana bir lid shuncha soniyada limitga yetsa — uni ham kutadi
BATCH_CAP = 60                 # lekin birinchisidan ko'pi bilan shuncha soniya
WARN_BEFORE = 5 * 60           # 🟡 doska: limitdan shuncha oldin (20 daq limit — 15 daqiqa kutgan)
CARD_WINDOW = 24 * 3600        # Push'dan keyin shu vaqt ichida karta yuborilsa — o'sha Push natijasi
CL_CAP = 12 * 3600             # mijozning bitta javob vaqti o'rtachaga ko'pi bilan shuncha qo'shiladi (tun va h.k.)
STAVKA_LATE = 60 * 60          # topik ochilganidan shuncha vaqt ichida stavka kech aniqlansa ham boshlanadi
SILENT_SLOTS = 3               # «ставка» eslatmasi o'chiq (0) bo'lsa: shuncha «navbat» jim o'tgach stavka tugaydi
REMIND_GIVEUP = 5 * 60         # «ставка» yuborilmasa: shuncha vaqt qayta urinadi, keyin «navbat» o'tgan hisoblanadi


def parse_cmds(text: str | None) -> set[str]:
    """«/rek /dep, cash» -> {'/rek', '/dep', '/cash'}."""
    out = set()
    for w in re.split(r"[\s,;]+", (text or "").strip().lower()):
        w = w.lstrip("/")
        if re.fullmatch(r"[a-z0-9_]{1,32}", w):
            out.add("/" + w)
    return out

# qaror kodlari (jurnal va «Lidni tekshirish» ekrani uchun)
DECISIONS = ("dup", "service", "ours", "excluded", "before", "stavka_skip", "stavka_bet", "bet_text", "stavka_end",
             "auto_bet", "wait", "wait_more", "reply", "staff", "alert", "late_bet")


@dataclass
class Msg:
    chat_id: int
    topic_id: int
    msg_id: int
    ts: int
    sender_id: int | None
    who: str                 # client | staff | ours | service
    video: bool = False      # dumaloq video (video_note)
    source: str = "live"     # live | catchup
    cmd: str = ""            # xodimning buyrug'i («/rek») — faqat buyruq so'zi, matn emas


def skip_list(db: Database) -> list[str]:
    raw = db.get("skip_emojis")
    return [ch for ch in raw if not ch.isspace() and ch not in ",;️‍"]


def label_excluded(label: str, skip: list[str]) -> bool:
    t = "".join(ch for ch in (label or "").lstrip() if ch not in ("️", "‍"))
    return any(t.startswith(e) for e in skip)


class Tracker:
    def __init__(self, db: Database, tz: ZoneInfo, notifier, clock=time.time):
        self.db = db
        self.tz = tz
        self.notifier = notifier
        self.clock = clock
        self.chat_folder: dict[int, int] = {}
        self.forums: set[int] = set()
        self.on_staff = None             # xodim lidga yozdi -> ishga kelgan (Attendance.work_seen)
        self.main_id: int | None = None  # asosiy akkaunt (papka uchun Push akkaunti bo'lsa — xodimni aniqlash)
        self._due_since: dict[int, int] = {}
        self._tasks: set = set()
        self.reload()

    def _bg(self, coro) -> None:
        """«Проёб»dagi xabarni tahrirlash / yuborish — fonda. Lid xabarini qayta ishlash Telegram javobini (yoki
        «sekinlang» kutishini) kutib qolmaydi: aks holda bot keyingi xabarlarni kech ko'radi (noto'g'ri «задержка»)."""
        import asyncio

        async def run():
            try:
                await coro
            except Exception:
                log.exception("«Проёб» xabari (fonda)")
        try:
            task = asyncio.get_running_loop().create_task(run())
        except RuntimeError:
            coro.close()
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def settle(self) -> None:
        """Fondagi «Проёб» xabarlari tugashini kutish (sinov va to'xtash uchun)."""
        import asyncio
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ------------------------------------------------------------ keshlar
    def reload(self) -> None:
        rows = self.db.all("SELECT chat_id, folder_id, is_forum FROM chats")
        self.chat_folder = {r["chat_id"]: r["folder_id"] for r in rows}
        self.forums = {r["chat_id"] for r in rows if r["is_forum"]}

    def is_monitored(self, chat_id: int) -> bool:
        return chat_id in self.chat_folder

    def stavka_limits(self) -> tuple[int, int, int, int]:
        """(nechta video, eslatma soniyada, kech aniqlash oynasi soniyada, video matni oynasi soniyada).
        Stavkaning vaqt chegarasi yo'q: N video bilan yoki oxirgi «ставка» eslatmasidan keyin tugaydi."""
        need = max(1, self.db.get_int("stavka_count", 3))
        remind = max(1, self.db.get_int("stavka_next", 20)) * 60
        window = max(10, self.db.get_int("bet_text_seconds", 120))
        return need, remind, STAVKA_LATE, window

    def remind_rules(self) -> tuple[int, int, int]:
        """(birinchi stavka uchun soniya, keyingilari uchun soniya, bitta lidga eng ko'p eslatma)."""
        return (max(1, self.db.get_int("stavka_first", 20)) * 60, max(1, self.db.get_int("stavka_next", 20)) * 60,
                max(0, self.db.get_int("stavka_max_remind", 3)))

    def remind_limit(self) -> int:
        """Nechta «navbat»dan keyin stavka tugaydi (eslatma o'chiq bo'lsa ham — jim «navbat»lar)."""
        return self.remind_rules()[2] or SILENT_SLOTS

    def work_window(self):
        try:
            return parse_hhmm(self.db.get("work_start")), parse_hhmm(self.db.get("work_end"))
        except ValueError:
            return parse_hhmm("10:00"), parse_hhmm("23:00")

    def label(self, chat_id: int, topic_id: int) -> str:
        if topic_id:
            t = self.db.one("SELECT icon, title FROM topics WHERE chat_id=? AND topic_id=?", (chat_id, topic_id))
            return f"{t['icon']} {t['title']}".strip() if t else ""
        c = self.db.one("SELECT title FROM chats WHERE chat_id=?", (chat_id,))
        return c["title"] if c else ""

    # ------------------------------------------------------------ kim yozdi
    def person_of(self, chat_id: int, sender_id: int | None, ts: int | None = None):
        """Xabarni yozgan xodim. O'z akkauntidan yozsa — aniq (Telegram ID yoki @username bo'yicha). Papka
        akkauntidan (shu papkaning Push akkaunti yoki asosiy akkaunt) yozsa — o'sha kuni shu RD da ishlayotgan xodim
        (📅 Bugun kim qayerda). Aniqlab bo'lmasa — None (taxmin qilinmaydi)."""
        if not sender_id:
            return None
        p = P.by_tg(self.db, sender_id)
        if p is not None:
            return p
        fid = self.chat_folder.get(chat_id)
        f = P.folder(self.db, fid) if fid else None
        if f is None or not f["push_account_id"]:
            return None
        if f["push_account_id"] == -1:
            acc_uid = self.main_id
        else:
            row = self.db.one("SELECT user_id FROM accounts WHERE id=?", (f["push_account_id"],))
            acc_uid = row["user_id"] if row else None
        if not acc_uid or int(acc_uid) != int(sender_id):
            return None
        ppl = R.workers(self.db, fid, local_date(ts or self.clock(), self.tz))
        return ppl[0] if len(ppl) == 1 else None

    def day_of(self, ts: int | None = None):
        return local_date(ts or self.clock(), self.tz)

    def workers(self, fid: int | None, ts: int | None = None) -> list:
        """Shu kuni shu RD da ishlaydigan xodim(lar) — belgilash va jarima shular bo'yicha."""
        return R.workers(self.db, fid, self.day_of(ts)) if fid else []

    def card_cmds(self, fid: int | None = None) -> set[str]:
        """Karta buyruqlari — hamma RD uchun bitta ro'yxat (CRM egasi o'zgartirsa, panelda yangilanadi)."""
        return parse_cmds(self.db.get("card_cmds"))

    async def _staff_seen(self, m: "Msg") -> None:
        """Xodim lidga yozdi — demak ishda (faqat bugungi xabarlar, yangi versiya ishga tushgandan keyin)."""
        if self.on_staff is None or m.ts < self.db.get_int("cards_since") \
                or local_date(m.ts, self.tz) != local_date(self.clock(), self.tz):
            return
        p = self.person_of(m.chat_id, m.sender_id, m.ts)
        if p is not None:
            self._bg(self.on_staff(p, m.ts))

    def _push_hit(self, c: int, t: int, ts: int, col: str, window: int) -> None:
        """Oxirgi Push (shu oyna ichida) natijasiga yozish: mijoz yozdi (replied_ts) yoki karta ketdi (card_ts)."""
        row = self.db.one("SELECT rowid AS rid, replied_ts, card_ts FROM push_log WHERE chat_id=? AND topic_id=? "
                          "AND ts<=? AND ts>=? ORDER BY ts DESC LIMIT 1", (c, t, ts, ts - window))
        if row is not None and row[col] is None:
            self.db.run(f"UPDATE push_log SET {col}=? WHERE rowid=?", (ts, row["rid"]))

    def _client_spoke(self, th, m: "Msg") -> None:
        """Haqiqiy mijoz xabari: u odatda qancha vaqtda javob qaytarishi (soviyotgan lid) va Push'ga javobmi."""
        c, t = m.chat_id, m.topic_id
        if th["cl_turn"] is not None and m.ts >= th["cl_turn"]:
            n = min(th["cl_n"] or 0, 9)                     # oxirgi ~10 ta javob og'irligida o'rtacha
            ws, we = self.work_window()                     # tun hisobga kirmaydi (ish vaqtidagi soniyalar)
            lat = work_seconds(th["cl_turn"], m.ts, self.tz, ws, we)
            avg = ((th["cl_avg"] or 0) * n + min(lat, CL_CAP)) / (n + 1)
            self._set(c, t, cl_turn=None, cl_avg=int(round(avg)), cl_n=(th["cl_n"] or 0) + 1)
        self._push_hit(c, t, m.ts, "replied_ts", max(1, self.db.get_int("push_reply_min", 90)) * 60)

    async def _command(self, th, m: "Msg") -> str:
        """Xodimning /buyrug'i. Karta buyrug'i (/rek …) — lidga karta ketdi: yoziladi va bu mijozga javob ham.
        Boshqa buyruqlar (/status …) — ichki ish: mijozga javob ham, mijoz xabari ham emas."""
        c, t = m.chat_id, m.topic_id
        upd = {"last_staff_ts": max(m.ts, th["last_staff_ts"] or 0)}
        fid = self.chat_folder.get(c)
        card = fid is not None and m.cmd in self.card_cmds(fid)
        if card and th["cl_turn"] is None and th["stavka"] != "on":
            upd["cl_turn"] = m.ts                             # karta ketdi — endi mijoz navbati
        self._set(c, t, **upd)
        await self._staff_seen(m)
        if not card:
            return "command"
        p = self.person_of(c, m.sender_id, m.ts)
        new = self.db.run("INSERT OR IGNORE INTO cards(chat_id, msg_id, topic_id, folder_id, sender_id, person_id, "
                          "cmd, ts) VALUES(?,?,?,?,?,?,?,?)", (c, m.msg_id, t, fid, m.sender_id, p["id"] if p else None,
                                                               m.cmd, m.ts)).rowcount
        if new:
            self._push_hit(c, t, m.ts, "card_ts", CARD_WINDOW)
        if th["stavka"] != "on" and th["wait_since"] is not None and m.ts >= th["wait_since"]:
            await self._answered(th, m.ts, m.sender_id, by_button=None)
        return "card"

    # ------------------------------------------------------------ nitlar
    def thread(self, chat_id: int, topic_id: int):
        return self.db.one("SELECT * FROM threads WHERE chat_id=? AND topic_id=?", (chat_id, topic_id))

    def start_thread(self, chat_id: int, topic_id: int, created_ts: int | None) -> None:
        """Nitni birinchi marta ko'rdik. Yangi topik (o'rnatilgandan keyin ochilgan) — stavka boshlanadi."""
        if self.thread(chat_id, topic_id) is not None:
            return
        stavka, start = "", None
        since = self.db.get_int("delay_from")
        if topic_id > 1 and created_ts and self.db.flag("stavka_enabled") and created_ts >= since:
            stavka, start = "on", int(created_ts)
        self.db.run("INSERT OR IGNORE INTO threads(chat_id, topic_id, stavka, stavka_from) VALUES(?,?,?,?)",
                    (chat_id, topic_id, stavka, start))
        if stavka:
            log.info("Stavka: yangi lid %s/%s", chat_id, topic_id)

    def _set(self, chat_id: int, topic_id: int, **fields) -> None:
        cols = ", ".join(f"{k}=?" for k in fields)
        self.db.run(f"UPDATE threads SET {cols} WHERE chat_id=? AND topic_id=?",
                    tuple(fields.values()) + (chat_id, topic_id))

    def _journal(self, m: Msg, decision: str, kind: str = "") -> None:
        try:
            self.db.run("INSERT INTO journal(at, ts, chat_id, topic_id, msg_id, sender_id, who, kind, source, decision) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (int(self.clock()), m.ts, m.chat_id, m.topic_id, m.msg_id, m.sender_id, m.who,
                         kind or ("video" if m.video else "text"), m.source, decision))
        except Exception:
            log.exception("journal")

    # ------------------------------------------------------------ bitta xabar
    async def handle(self, m: Msg) -> str:
        """Xabar → qaror. Nit avval start_thread() bilan yaratilgan bo'lishi kerak (yo'q bo'lsa — eski lid)."""
        if self.thread(m.chat_id, m.topic_id) is None:
            self.start_thread(m.chat_id, m.topic_id, None)
        th = self.thread(m.chat_id, m.topic_id)
        if m.msg_id <= th["seen_msg_id"]:
            return "dup"
        self._set(m.chat_id, m.topic_id, seen_msg_id=m.msg_id, last_activity=max(th["last_activity"], m.ts))
        decision = await self._decide(th, m)
        self._journal(m, decision)
        return decision

    async def handle_late(self, m: Msg) -> str:
        """Kech topilgan xabar: Telegram jonli yetkazmagan, bu nitda undan YANGI xabar allaqachon ishlangan.
        Muhimi — xodim javobi: mijoz kutayotgan bo'lsa, kutish o'sha javob vaqtida yopiladi (noto'g'ri «задержка»
        bo'lmasin), javobdan keyin yozgan mijoz xabari bo'lsa — kutish o'shandan qayta boshlanadi."""
        c, t = m.chat_id, m.topic_id
        th = self.thread(c, t)
        if th is None or self.db.one("SELECT 1 FROM journal WHERE chat_id=? AND topic_id=? AND msg_id=?",
                                     (c, t, m.msg_id)):
            return "dup"
        if m.video and m.who in ("client", "staff") and th["stavka"] == "on":
            # stavka videosi kech topildi (Telegram jonli yetkazmagan) — baribir stavka sanaladi
            new = self.db.run("INSERT OR IGNORE INTO bets(chat_id, topic_id, msg_id, ts) VALUES(?,?,?,?)",
                              (c, t, m.msg_id, m.ts)).rowcount
            if new:
                bets = (th["bets"] or 0) + 1
                self._set(c, t, bets=bets, bet_last_ts=max(m.ts, th["bet_last_ts"] or 0))
                if m.who == "client":
                    self._count_lead(th, m)
                need = self.stavka_limits()[0]
                if bets >= need:
                    self._finish_stavka(c, t, max(m.ts, th["bet_last_ts"] or 0), "late")
            self._journal(m, "late_bet")
            return "late_bet"
        if m.who == "client":
            self._count_lead(th, m)
            self._journal(m, "late_client")
            return "late_client"
        card = m.who == "service" and m.cmd and m.cmd in self.card_cmds()
        if m.who != "staff" and not card:
            self._journal(m, "late_other")
            return "late_other"
        self._set(c, t, last_staff_ts=max(m.ts, th["last_staff_ts"] or 0))
        await self._staff_seen(m)
        if th["stavka"] == "on" or th["wait_since"] is None or m.ts < th["wait_since"]:
            self._journal(m, "late_staff")
            return "late_staff"
        await self._answered(th, m.ts, m.sender_id, by_button=None)
        nxt = self.db.one("SELECT ts, msg_id FROM journal WHERE chat_id=? AND topic_id=? AND who='client' AND ts>? "
                          "AND decision IN ('wait', 'wait_more', 'wait_last') ORDER BY ts, id LIMIT 1", (c, t, m.ts))
        if nxt is not None:
            self._set(c, t, wait_since=nxt["ts"], wait_msg_id=nxt["msg_id"], wait_first=nxt["ts"])
        self._journal(m, "late_reply")
        return "late_reply"

    def _fresh_topic(self, c: int, t: int, ts: int) -> int | None:
        """Yangi ochilgan topikmi (stavka davri ichida)? -> ochilgan vaqti yoki None."""
        if t <= 1 or not self.db.flag("stavka_enabled"):
            return None
        _need, _remind, cap, _w = self.stavka_limits()
        row = self.db.one("SELECT created_ts FROM topics WHERE chat_id=? AND topic_id=?", (c, t))
        created = row["created_ts"] if row is not None and row["created_ts"] else None
        if created is None:
            return None
        if created < self.db.get_int("delay_from") or not 0 <= ts - created <= cap:
            return None
        return int(created)

    def _late_stavka(self, th, start: int, why: str, keep_msg: int | None = None) -> None:
        """Yangi lid stavkasi kech aniqlandi (topik ma'lumoti kechikdi): stavka shu topik ochilgan paytdan boshlanadi,
        shu paytgacha yozilgan kutish bekor, chiqqan «задержка» havolasi hisobga kirmaydi."""
        c, t = th["chat_id"], th["topic_id"]
        prev = self.db.scalar("SELECT COUNT(*) FROM bets WHERE chat_id=? AND topic_id=? AND ts>=? AND msg_id<>?",
                              (c, t, start, keep_msg or 0))
        self._set(c, t, stavka="on", stavka_from=start, bets=prev, bet_text_wait=0, stavka_end=None,
                  stavka_reminded=0, stavka_remind_ts=None, wait_since=None, wait_msg_id=None, wait_first=None,
                  alert_id=None)
        a = self.db.one("SELECT * FROM alerts WHERE id=?", (th["alert_id"],)) if th["alert_id"] else None
        if a is not None and a["status"] == "open":
            self.db.run("UPDATE alerts SET status='void', closed_ts=?, closed_by=? WHERE id=?",
                        (int(self.clock()), "ставка", a["id"]))
            if a["group_msg_id"]:
                self._bg(self.render_alert_message(a["group_chat_id"], a["group_msg_id"]))
        log.info("Stavka: %s/%s kech aniqlandi (%s)", c, t, why)

    def topic_known(self, c: int, t: int) -> None:
        """Topik ma'lumoti keldi (sinxron): yangi topik bo'lib chiqsa, stavka hali boshlanmagan bo'lsa — boshlanadi."""
        th = self.thread(c, t)
        if th is None or th["stavka"] != "":
            return
        start = self._fresh_topic(c, t, int(self.clock()))
        if start is not None:
            self._late_stavka(th, start, "topik ma'lumoti")

    async def _decide(self, th, m: Msg) -> str:
        c, t = m.chat_id, m.topic_id
        if m.who == "client" and m.video and th["stavka"] == "":
            start = self._fresh_topic(c, t, m.ts)            # CRM stavka videosi — demak yangi lid
            if start is not None:
                self._late_stavka(th, start, "stavka videosi", keep_msg=m.msg_id)
                th = self.thread(c, t)
        if m.who == "service":
            return await self._command(th, m) if m.cmd else "service"
        if m.who == "ours":
            return "ours"
        if m.who == "client":
            self._count_lead(th, m)
        if m.who == "staff":
            await self._staff_seen(m)

        # ── stavka (yangi lid): video + uning matni, N marta
        if th["stavka"] == "on" and m.who == "staff":
            self._set(c, t, last_staff_ts=max(m.ts, th["last_staff_ts"] or 0))
        if th["stavka"] == "on":
            need, _remind, _late, window = self.stavka_limits()
            bets = th["bets"]
            if bets >= need and th["bet_text_wait"] and m.ts - (th["bet_last_ts"] or 0) > window:
                self._finish_stavka(c, t, (th["bet_last_ts"] or m.ts) + window, "window")
            elif m.video and m.who in ("client", "staff"):
                # stavka: vositachi botning avtostavkasi YOKI tushmasa — xodimning o'zi yuborgan dumaloq videosi
                new = self.db.run("INSERT OR IGNORE INTO bets(chat_id, topic_id, msg_id, ts) VALUES(?,?,?,?)",
                                  (c, t, m.msg_id, m.ts)).rowcount
                if new:
                    bets += 1
                self._set(c, t, bets=bets, bet_last_ts=m.ts, bet_text_wait=1 if m.who == "client" else 0)
                if m.who == "staff" and bets >= need:
                    self._finish_stavka(c, t, m.ts, "staff")
                    return "stavka_end"
                return "stavka_bet"
            elif m.who == "client" and th["bet_text_wait"] and m.ts - (th["bet_last_ts"] or 0) <= window:
                self._set(c, t, bet_text_wait=0)
                if bets >= need:
                    self._finish_stavka(c, t, m.ts, "text")
                    return "stavka_end"
                return "bet_text"
            elif bets >= need and not th["bet_text_wait"]:
                self._finish_stavka(c, t, th["bet_last_ts"] or m.ts, "bets")
            else:
                return "stavka_skip"
            th = self.thread(c, t)
            if th["stavka"] == "on":
                return "stavka_skip"

        # ── oddiy rejim
        if m.who == "client":
            _need, _remind, _cap, window = self.stavka_limits()
            if m.video:                                    # vositachi botning dumaloq videosi = avtostavka, javob kutmaydi
                self.db.run("INSERT OR IGNORE INTO bets(chat_id, topic_id, msg_id, ts) VALUES(?,?,?,?)",
                            (c, t, m.msg_id, m.ts))
                self._set(c, t, bet_last_ts=m.ts, bet_text_wait=1)
                return "auto_bet"
            if th["bet_text_wait"] and m.ts - (th["bet_last_ts"] or 0) <= window:
                self._set(c, t, bet_text_wait=0)           # video bilan keladigan matn — stavkaning o'zi
                return "bet_text"
            if th["bet_text_wait"]:
                self._set(c, t, bet_text_wait=0)
            echo = max(0, self.db.get_int("echo_seconds", 2))
            if echo and th["last_staff_ts"] is not None and 0 <= m.ts - th["last_staff_ts"] <= echo:
                return "echo"                              # xodim amalidan so'ng vositachi bot darhol yozgan — mijoz emas
            self._client_spoke(th, m)
            if m.ts < self.db.get_int("delay_from"):
                return "before"
            ws, we = self.work_window()
            if not is_work_time(m.ts, self.tz, ws, we):
                return "night"                             # ish vaqtidan tashqari — zaderjka hisoblanmaydi
            if label_excluded(self.label(c, t), skip_list(self.db)):
                return "excluded"
            if th["wait_since"] is None:
                self._set(c, t, wait_since=m.ts, wait_msg_id=m.msg_id, wait_first=m.ts)
                return "wait"
            # ketma-ket yozdi (birinchi xabaridan N daqiqa ichida) — zaderjka oxirgi xabaridan hisoblanadi
            slide = max(0, self.db.get_int("wait_slide_min", 5)) * 60
            first = th["wait_first"] or th["wait_since"]
            if slide and th["alert_id"] is None and th["wait_since"] < m.ts <= first + slide:
                self._set(c, t, wait_since=m.ts, wait_msg_id=m.msg_id)
                return "wait_last"
            return "wait_more"

        # odam (xodim) yozdi
        upd = {"last_staff_ts": max(m.ts, th["last_staff_ts"] or 0)}
        if th["cl_turn"] is None:
            upd["cl_turn"] = m.ts                             # endi mijoz navbati (u qancha vaqtda javob qaytaradi)
        self._set(c, t, **upd)
        if th["wait_since"] is not None:
            if m.ts < th["wait_since"]:
                return "staff"
            await self._answered(th, m.ts, m.sender_id, by_button=None)
            return "reply"
        return "staff"

    def _count_lead(self, th, m: Msg) -> None:
        track = self.db.get_int("track_ts")
        if m.ts < track:
            return
        first = th["first_seen"] if th["first_seen"] is not None else m.ts
        self.db.run("UPDATE threads SET first_seen=?, last_seen=MAX(COALESCE(last_seen,0), ?), msg_count=msg_count+1 "
                    "WHERE chat_id=? AND topic_id=?", (min(first, m.ts), m.ts, m.chat_id, m.topic_id))

    def _finish_stavka(self, c: int, t: int, end_ts: int, why: str) -> None:
        self._set(c, t, stavka="done", stavka_end=int(end_ts), bet_text_wait=0)
        log.info("Stavka: %s/%s tugadi (%s)", c, t, why)

    # ------------------------------------------------------------ javob
    def elapsed(self, folder_id: int, since: int, now: int) -> int:
        """Ish vaqtidagi kutish soniyalari, papkaning hamma xodimi tanaffusda bo'lgan vaqtlarsiz."""
        ws, we = self.work_window()
        total = work_seconds(since, now, self.tz, ws, we)
        for p in self.db.all("SELECT start_ts, end_ts FROM pauses WHERE folder_id=? AND start_ts<? "
                             "AND (end_ts IS NULL OR end_ts>?)", (folder_id, now, since)):
            a, b = max(since, p["start_ts"]), min(now, p["end_ts"] or now)
            if b > a:
                total -= work_seconds(a, b, self.tz, ws, we)
        return max(0, total)

    async def _answered(self, th, ts: int, staff_id: int | None, by_button: str | None) -> None:
        """Kutish yopildi: javob yozildi yoki «✅ Выполнено» bosildi."""
        c, t = th["chat_id"], th["topic_id"]
        # Nit holati bazadan YANGIDAN o'qiladi: shu xabar ishlanayotganda (masalan «Опоздание» yuborilayotganda)
        # «задержка» ketgan bo'lishi mumkin — eski nusxada alert_id yo'q, javob esa havolani yopishi kerak.
        th = self.thread(c, t)
        if th is None or th["wait_since"] is None:
            return
        fid = self.chat_folder.get(c)
        waited = self.elapsed(fid, th["wait_since"], ts) if fid else 0
        p = self.person_of(c, staff_id, ts) if staff_id else None
        self.db.run("INSERT INTO replies(chat_id, topic_id, folder_id, staff_id, wait_since, reply_ts, work_seconds, "
                    "person_id) VALUES(?,?,?,?,?,?,?,?)", (c, t, fid or 0, staff_id, th["wait_since"], ts, waited,
                                                          p["id"] if p else None))
        self._set(c, t, wait_since=None, wait_msg_id=None, alert_id=None)
        if th["alert_id"]:
            await self._close_alert(th["alert_id"], ts, waited, staff_id, by_button, person=p)

    async def _close_alert(self, alert_id: int, ts: int, waited: int, staff_id: int | None,
                           by_button: str | None, person=None) -> None:
        """Havola yopildi (javob yoki «✅ Выполнено»). Jarima bu yerda emas — eslatmadan keyin (_remind_alerts)."""
        a = self.db.one("SELECT * FROM alerts WHERE id=?", (alert_id,))
        if a is None or a["status"] != "open":
            return
        status = "done" if by_button else "answered"
        who = by_button or (P.mention(person) if person is not None else self._staff_name(staff_id))
        self.db.run("UPDATE alerts SET status=?, closed_ts=?, closed_by=?, waited_min=? WHERE id=?",
                    (status, ts, who, minutes_up(waited), alert_id))
        if a["group_msg_id"]:
            self._bg(self.render_alert_message(a["group_chat_id"], a["group_msg_id"]))

    def _staff_name(self, uid: int | None) -> str:
        if uid is None:
            return "менеджер"
        p = P.by_tg(self.db, uid)
        if p is not None:
            return P.mention(p)
        h = self.db.one("SELECT name FROM known_humans WHERE user_id=?", (uid,))
        return h["name"] if h and h["name"] else "менеджер"

    def warn_seconds(self) -> int:
        """🟡 chegarasi: limitdan 5 daqiqa oldin (20 daq limit — 15 daqiqa kutgan)."""
        limit = max(1, self.db.get_int("limit_minutes", 20)) * 60
        return max(60, limit - WARN_BEFORE) if limit > WARN_BEFORE else max(60, limit // 2)

    def live_counts(self, now: int) -> dict:
        """Bosh menyu va 📌 doska uchun aniq, real vaqtdagi sonlar (zaderjka qoidalari bilan bir xil soat: faqat ish
        vaqti, tanaffus pauzasisiz, ⚡/💊 va stavkadagilarsiz):
        waiting — hozir javob kutayotgan lidlar; stavka — stavka bosqichidagi yangi lidlar;
        overdue — papka -> limitdan (20 daq) oshib javobsiz turganlar (🔴); near — papka -> 15–19 daq kutganlar (🟡)."""
        limit = max(1, self.db.get_int("limit_minutes", 20)) * 60
        warn = self.warn_seconds()
        skip = skip_list(self.db)
        on = {f["id"] for f in P.folders(self.db) if f["delay_on"]}
        out = {"waiting": 0, "stavka": 0, "overdue": {}, "near": {}, "wait_by": {}}
        for th in self.db.all("SELECT chat_id, topic_id, wait_since, stavka FROM threads "
                              "WHERE wait_since IS NOT NULL OR stavka='on'"):
            fid = self.chat_folder.get(th["chat_id"])
            if fid is None:
                continue                                   # papkada emas (nazoratda yo'q)
            if th["stavka"] == "on":
                out["stavka"] += 1
                continue
            if th["wait_since"] is None or fid not in on or label_excluded(self.label(th["chat_id"], th["topic_id"]),
                                                                           skip):
                continue
            out["waiting"] += 1
            out["wait_by"][fid] = out["wait_by"].get(fid, 0) + 1     # 👥 jonli xodimlar: RD bo'yicha
            waited = self.elapsed(fid, th["wait_since"], now)
            if waited >= limit:
                out["overdue"][fid] = out["overdue"].get(fid, 0) + 1
            elif waited >= warn:
                out["near"][fid] = out["near"].get(fid, 0) + 1
        return out

    def overdue_now(self, now: int) -> dict[int, int]:
        return self.live_counts(now)["overdue"]

    async def status_changed(self, chat_id: int, topic_id: int) -> bool:
        """Lid statusi (topik belgisi) ⚡/💊 ga o'zgardi: bunday lid zaderjka emas — kutish bekor, ochiq
        «задержка» havolasi yopiladi va hisobga kirmaydi (void). -> bekor qilindimi."""
        label = self.label(chat_id, topic_id)
        if not label_excluded(label, skip_list(self.db)):
            return False
        th = self.thread(chat_id, topic_id)
        if th is None or (th["wait_since"] is None and not th["alert_id"]):
            return False
        now = int(self.clock())
        self._set(chat_id, topic_id, wait_since=None, wait_msg_id=None, alert_id=None)
        a = self.db.one("SELECT * FROM alerts WHERE id=?", (th["alert_id"],)) if th["alert_id"] else None
        if a is not None and a["status"] == "open":
            self.db.run("UPDATE alerts SET status='void', closed_ts=?, closed_by=? WHERE id=?",
                        (now, f"статус {label.split()[0]}", a["id"]))
            if a["group_msg_id"]:
                self._bg(self.render_alert_message(a["group_chat_id"], a["group_msg_id"]))
        log.info("Status %s: %s/%s — zaderjka emas", label[:2], chat_id, topic_id)
        return True

    async def press_done(self, alert_id: int, who: str) -> int:
        """«✅ Выполнено» guruhda bosildi: shu xabardagi hamma ochiq havolalar yopiladi. -> nechta yopildi."""
        a = self.db.one("SELECT * FROM alerts WHERE id=?", (alert_id,))
        if a is None:
            return 0
        rows = self.db.all("SELECT * FROM alerts WHERE group_chat_id=? AND group_msg_id=? AND status='open'",
                           (a["group_chat_id"], a["group_msg_id"])) if a["group_msg_id"] else [a]
        now = int(self.clock())
        for r in rows:
            th = self.thread(r["chat_id"], r["topic_id"])
            if th is not None and th["alert_id"] == r["id"] and th["wait_since"] is not None:
                await self._answered(th, now, None, by_button=who)
            else:
                await self._close_alert(r["id"], now, 0, None, who)
        return len(rows)

    # ------------------------------------------------------------ alert matni (guruh uchun ruscha)
    def alert_message_text(self, gid: int, mid: int) -> tuple[str, bool]:
        """Bitta guruh xabaridagi hamma havolalar: ochiqlari oddiy, yopilganlari ✅. -> (matn, hammasi yopildimi)."""
        rows = self.db.all("SELECT * FROM alerts WHERE group_chat_id=? AND group_msg_id=? ORDER BY wait_since, id",
                           (gid, mid))
        return self._compose(rows)

    def hm(self, ts) -> str:
        return datetime.fromtimestamp(ts, self.tz).strftime("%H:%M") if ts else ""

    def _compose(self, rows) -> tuple[str, bool]:
        """«Проёб»: mayda «Rd 2 · задержка · ждёт с 14:49» → havolalar (oddiy) → mayda @xodim / «выполнено — @kim»."""
        if not rows:
            return "", True
        f = P.folder(self.db, rows[0]["folder_id"])
        closed = all(r["status"] != "open" for r in rows)
        since = min((r["wait_since"] for r in rows if r["wait_since"]), default=None)
        lines = [head(f["name"] if f else "", "задержка", f"ждёт с {self.hm(since)}" if since else "")]
        lines += [link(message_link(r["chat_id"], r["wait_msg_id"] or r["topic_id"], r["topic_id"]),
                       done=r["status"] != "open") for r in rows]
        if closed:
            whos = []
            for r in rows:
                if r["closed_by"] and r["closed_by"] not in whos:
                    whos.append(r["closed_by"])
            lines.append(small("выполнено" + (f" — {esc(', '.join(whos))}" if whos else "")))
        else:
            people = self.workers(f["id"], rows[0]["created_ts"]) if f else []
            lines += self.break_lines(people)
            lines.append(tag(people))
        return "\n".join(x for x in lines if x), closed

    def break_lines(self, people, now: int | None = None) -> list[str]:
        """«☕ Baxa на перерыве до 14:30» — belgilanganlardan tanaffusdagilari (mayda)."""
        from .attendance import break_until
        now = int(self.clock() if now is None else now)
        out = []
        for p in people:
            until = break_until(self.db, p["id"], now)
            if until:
                out.append(small(f"☕ {esc(p['name'])} на перерыве до {self.hm(until)}"))
        return out

    async def render_alert_message(self, gid: int, mid: int) -> None:
        text, closed = self.alert_message_text(gid, mid)
        if not text:
            return
        first = self.db.scalar("SELECT MIN(id) FROM alerts WHERE group_chat_id=? AND group_msg_id=?", (gid, mid))
        try:
            await self.notifier.edit_group(gid, mid, text, done_button=None if closed else first)
        except Exception as exc:
            log.info("Alert tahrirlanmadi: %s", exc)
        if closed:                                     # 🧹 hamma lidga javob berildi — N daqiqadan keyin o'chadi
            from .tidy import remember
            remember(self.db, gid, mid, "delay", int(self.clock()))

    # ------------------------------------------------------------ taymer (har ~10 soniyada)
    async def tick(self, now: int | None = None) -> dict:
        now = int(self.clock() if now is None else now)
        out = {"alerts": 0, "stavka_done": 0, "reminders": 0}
        if not self.db.flag("bot_enabled"):
            return out
        out["stavka_done"] = self._stavka_timeouts(now)
        out["reminders"] = await self._stavka_reminders(now)
        if self.db.flag("delay_enabled"):
            out["alerts"] = await self._delays(now)
            out["eod"] = await self.end_of_day(now)
            out["reminded"] = await self._remind_alerts(now)
        return out

    def _stavka_timeouts(self, now: int) -> int:
        """Stavka tugashi: N video (va oxirgisining matni) keldi — yoki hamma «ставка» eslatmalari ketdi (sozlama
        kamaytirilgan bo'lsa ham shu yerda). Vaqt chegarasi yo'q."""
        need, _remind, _late, window = self.stavka_limits()
        limit = self.remind_limit()
        done = 0
        for th in self.db.all("SELECT * FROM threads WHERE stavka='on'"):
            if th["bets"] >= need and (not th["bet_text_wait"] or now - (th["bet_last_ts"] or 0) > window):
                end = (th["bet_last_ts"] or now) + (window if th["bet_text_wait"] else 0)
                self._finish_stavka(th["chat_id"], th["topic_id"], min(end, now), "timer")
                done += 1
            elif th["bets"] < need and th["stavka_reminded"] >= limit:
                self._finish_stavka(th["chat_id"], th["topic_id"], th["stavka_remind_ts"] or now, "reminders")
                done += 1
        return done

    def _remind_step(self, th, now: int, limit: int) -> None:
        """Bitta «ставка» navbati o'tdi. Oxirgisi bo'lsa — stavka tugaydi: endi mijoz xabarlari oddiy zaderjka."""
        n = (th["stavka_reminded"] or 0) + 1
        self._set(th["chat_id"], th["topic_id"], stavka_reminded=n, stavka_remind_ts=now)
        if n >= limit:
            self._finish_stavka(th["chat_id"], th["topic_id"], now, "reminders")

    async def _stavka_reminders(self, now: int) -> int:
        """«ставка»: yangi chatdan keyin birinchi stavka N daqiqada, keyingisi oldingisidan (yoki eslatmadan)
        M daqiqada kelmasa — eslatma. Bitta lidga ko'pi bilan K marta; K-eslatmadan keyin stavka tugaydi.
        Faqat ish vaqtida (kechasi navbat ham o'tmaydi)."""
        need, _next, _late, _window = self.stavka_limits()
        first, nxt, max_n = self.remind_rules()
        limit = self.remind_limit()
        ws, we = self.work_window()
        if not is_work_time(now, self.tz, ws, we):
            return 0
        by_folder: dict[int, list] = {}
        quiet = []                                   # eslatma o'chiq: navbat jim o'tadi
        for th in self.db.all("SELECT * FROM threads WHERE stavka='on' AND stavka_reminded<? AND bets<?",
                              (limit, need)):
            fid = self.chat_folder.get(th["chat_id"])
            if fid is None:
                continue
            anchor = max(th["stavka_from"] or 0, th["bet_last_ts"] or 0, th["stavka_remind_ts"] or 0)
            gap = first if (not th["bets"] and not th["stavka_reminded"]) else nxt
            if now < anchor + gap:
                continue
            if max_n:
                by_folder.setdefault(fid, []).append((th, anchor + gap))
            else:
                quiet.append(th)
        for th in quiet:
            self._remind_step(th, now, limit)
        sent = 0
        for fid, items in by_folder.items():
            f = P.folder(self.db, fid)
            since = min((th["stavka_from"] for th, _due in items if th["stavka_from"]), default=None)
            text = "\n".join(x for x in (
                [head(f["name"] if f else "", "ставка", f"новый чат с {self.hm(since)}" if since else "")]
                + [link(message_link(th["chat_id"], th["seen_msg_id"] or th["topic_id"], th["topic_id"]))
                   for th, _due in items]
                + [tag(self.workers(fid, now))]) if x)
            try:
                await self.notifier.send_group(text, trash="info")
            except Exception as exc:
                log.warning("«ставка» yuborilmadi: %s", exc)
                # bir necha daqiqa qayta urinadi; keyin ham bo'lmasa — navbat o'tgan hisoblanadi (stavka osilib qolmasin)
                items = [(th, due) for th, due in items if now - due >= REMIND_GIVEUP]
            else:
                sent += len(items)
            for th, _due in items:
                self._remind_step(th, now, limit)
        return sent

    # ------------------------------------------------------------ ish tugadi: javobsiz qolganlar
    async def end_of_day(self, now: int) -> int:
        """Ish tugagach (1 daqiqadan keyin) javobsiz chatlar «Проёб»ga: «ishni oxirigacha yetkazing».
        Ertalab ular uchun zaderjka bo'lmaydi (kutish yopiladi)."""
        if not self.db.flag("eod_enabled"):
            return 0
        ws, we = self.work_window()
        t = datetime.fromtimestamp(now, self.tz)
        end_dt = datetime.combine(t.date(), we, tzinfo=self.tz)
        if end_dt > t:
            end_dt -= timedelta(days=1)
        end_ts = int(end_dt.timestamp())
        key = end_dt.date().isoformat()
        # faqat ish tugagandan 1 daqiqa – 3 soat oralig'ida va ish vaqti bo'lmaganda (qayta ishga tushganda kun o'rtasida emas)
        if not end_ts + 60 <= now <= end_ts + 3 * 3600 or is_work_time(now, self.tz, ws, we) \
                or self.db.get("eod_last") >= key:
            return 0
        self.db.set("eod_last", key)
        skip = skip_list(self.db)
        by_folder: dict[int, list] = {}
        for th in self.db.all("SELECT * FROM threads WHERE wait_since IS NOT NULL AND stavka<>'on' ORDER BY wait_since"):
            fid = self.chat_folder.get(th["chat_id"])
            f = P.folder(self.db, fid) if fid else None
            if f is None or not f["delay_on"] or label_excluded(self.label(th["chat_id"], th["topic_id"]), skip):
                continue
            by_folder.setdefault(fid, []).append(th)
        sent = 0
        for fid, items in by_folder.items():
            f = P.folder(self.db, fid)
            for i in range(0, len(items), MAX_LINKS):
                part = items[i:i + MAX_LINKS]
                text = "\n".join(x for x in (
                    [head(f["name"], "рабочий день закончился", "без ответа")]
                    + [link(message_link(th["chat_id"], th["wait_msg_id"] or th["topic_id"], th["topic_id"]))
                       for th in part]
                    + [tag(self.workers(fid, end_ts), "доведите работу до конца, чтобы ни один чат "
                                                        "не остался без ответа")]) if x)
                try:
                    await self.notifier.send_group(text, trash="info")
                    sent += len(part)
                except Exception as exc:
                    log.warning("Kun oxiri eslatmasi yuborilmadi: %s", exc)
        # ertalab ular uchun zaderjka bo'lmaydi
        self.db.run("UPDATE threads SET wait_since=NULL, wait_msg_id=NULL, alert_id=NULL WHERE wait_since IS NOT NULL")
        return sent

    async def _delays(self, now: int) -> int:
        """Limitdan oshgan lidlar — papka bo'yicha bitta «задержка». Birinchisidan 40 soniya kutadi (shu orada
        kechikkanlar birga ketadi); shunda yana bir lid 10 soniyada limitga yetadigan bo'lsa — uni ham kutadi
        (ko'pi bilan 1 daqiqa)."""
        limit = max(1, self.db.get_int("limit_minutes", 20)) * 60
        folders = {f["id"]: f for f in P.folders(self.db)}
        skip = skip_list(self.db)
        due: dict[int, list] = {}
        soon: set[int] = set()
        for th in self.db.all("SELECT * FROM threads WHERE wait_since IS NOT NULL AND alert_id IS NULL "
                              "ORDER BY wait_since"):
            fid = self.chat_folder.get(th["chat_id"])
            f = folders.get(fid)
            if f is None or not f["delay_on"] or th["stavka"] == "on":
                continue
            if label_excluded(self.label(th["chat_id"], th["topic_id"]), skip):
                self._set(th["chat_id"], th["topic_id"], wait_since=None, wait_msg_id=None)
                continue
            waited = self.elapsed(fid, th["wait_since"], now)
            if waited >= limit:
                due.setdefault(fid, []).append(th)
            elif waited >= limit - BATCH_LOOK:
                soon.add(fid)
        batch = BATCH_SEC if self.db.flag("delay_batch") else 0
        for fid in [x for x in self._due_since if x not in due]:
            self._due_since.pop(fid, None)                 # kutayotganlar javob oldi — hisob boshidan
        sent = 0
        for fid, items in due.items():
            first = self._due_since.setdefault(fid, now)
            if batch and len(items) < MAX_LINKS:
                if now - first < batch:
                    continue                               # yana kechikkanlar bo'lsa — birga ketadi
                if fid in soon and now - first < BATCH_CAP:
                    continue                               # yana biri bir necha soniyada kechikadi — uni ham kutamiz
            self._due_since.pop(fid, None)
            for i in range(0, len(items), MAX_LINKS):
                sent += await self._send_alert(items[i:i + MAX_LINKS], folders[fid], now)
        return sent

    async def _send_alert(self, items: list, f, now: int) -> int:
        """Papka bo'yicha bitta «задержка» xabari: shu paytda kechikkan hamma lidlar birga (bittalab emas).
        Keyin kechikkanlari — pastga yangi xabar bo'lib; eski xabarlar o'chirilmaydi. -> nechta nit."""
        ids = []
        for th in items:
            cur = self.db.run("INSERT INTO alerts(chat_id, topic_id, folder_id, wait_since, wait_msg_id, created_ts) "
                              "VALUES(?,?,?,?,?,?)", (th["chat_id"], th["topic_id"], f["id"], th["wait_since"],
                                                      th["wait_msg_id"], now))
            ids.append(int(cur.lastrowid))
        q = ",".join("?" * len(ids))
        rows = self.db.all(f"SELECT * FROM alerts WHERE id IN ({q}) ORDER BY wait_since, id", ids)
        text, _ = self._compose(rows)
        try:
            gid, mid = await self.notifier.send_group(text, done_button=ids[0])
        except Exception as exc:
            self.db.run(f"DELETE FROM alerts WHERE id IN ({q})", ids)
            log.warning("«задержка» yuborilmadi: %s", exc)
            return 0
        self.db.run(f"UPDATE alerts SET group_chat_id=?, group_msg_id=? WHERE id IN ({q})", [gid, mid] + ids)
        answered_meanwhile = []
        for th, aid in zip(items, ids):
            # «задержка» yuborilayotgan soniyalarda xodim javob bergan bo'lishi mumkin — unda havola darhol yopiladi
            # (aks holda u «ochiq» qolib, javob berilgan lid uchun jarima yozilardi)
            cur = self.db.run("UPDATE threads SET alert_id=? WHERE chat_id=? AND topic_id=? AND wait_since IS NOT NULL "
                              "AND alert_id IS NULL", (aid, th["chat_id"], th["topic_id"])).rowcount
            if not cur:
                answered_meanwhile.append((th, aid))
                continue
            self.db.run("INSERT INTO journal(at, ts, chat_id, topic_id, msg_id, sender_id, who, kind, source, "
                        "decision) VALUES(?,?,?,?,?,?,?,?,?,?)", (now, th["wait_since"], th["chat_id"],
                                                                   th["topic_id"], th["wait_msg_id"], None, "", "",
                                                                   "timer", "alert"))
        for th, aid in answered_meanwhile:
            rep = self.db.one("SELECT staff_id, reply_ts, work_seconds FROM replies WHERE chat_id=? AND topic_id=? "
                              "AND wait_since=? ORDER BY id DESC LIMIT 1", (th["chat_id"], th["topic_id"],
                                                                            th["wait_since"]))
            await self._close_alert(aid, rep["reply_ts"] if rep else now, rep["work_seconds"] if rep else 0,
                                    rep["staff_id"] if rep else None, None)
        return len(items)

    # ------------------------------------------------------------ ⏰ javobsiz zaderjka: eslatma → 1 ta zaderjka (jarima)
    def alert_remind_rules(self) -> tuple[bool, int, int]:
        """(yoqiqmi, eslatma — zaderjkadan necha soniya, muhlat — eslatmadan necha soniya)."""
        return (self.db.flag("remind_on"), max(1, self.db.get_int("remind_min", 15)) * 60,
                max(1, self.db.get_int("remind_grace_min", 5)) * 60)

    def episode_sec(self) -> int:
        return max(0, self.db.get_int("fine_episode", 30)) * 60

    def _last_work_end(self, now: int) -> int:
        _ws, we = self.work_window()
        t = datetime.fromtimestamp(now, self.tz)
        end_dt = datetime.combine(t.date(), we, tzinfo=self.tz)
        if end_dt > t:
            end_dt -= timedelta(days=1)
        return int(end_dt.timestamp())

    async def _unanswered(self, gid: int, mid: int) -> list:
        """Shu zaderjka xabaridagi hali javobsiz havolalar. Kun oxirida kutish yopilgan bo'lsa ham, keyin javob
        berilgani (xodim yozgan) — yopiladi (✅)."""
        out = []
        for a in self.db.all("SELECT * FROM alerts WHERE group_chat_id=? AND group_msg_id=? AND status='open'",
                             (gid, mid)):
            th = self.thread(a["chat_id"], a["topic_id"])
            if th is not None and th["last_staff_ts"] and th["last_staff_ts"] >= a["wait_since"]:
                fid = a["folder_id"]
                await self._close_alert(a["id"], th["last_staff_ts"],
                                        self.elapsed(fid, a["wait_since"], th["last_staff_ts"]) if fid else 0, None, None)
                continue
            out.append(a)
        return out

    def _group_anchor(self, gid: int, mid: int) -> int:
        """Zaderjka qachon chiqqan (shu «задержка» xabari) — «bitta zaderjka» davri shundan hisoblanadi."""
        return int(self.db.scalar("SELECT MIN(created_ts) FROM alerts WHERE group_chat_id=? AND group_msg_id=?",
                                  (gid, mid), default=int(self.clock())))

    def _remind_text(self, f, rows, people, grace: int, now: int, anchor: int) -> str:
        """«RD 1 · всё ещё без ответа / havolalar / ⏰ Ответьте в течение 5 мин — иначе штраф 5 $ / @baxa».
        Summalar har xil bo'lsa: «иначе штраф: @baxa 5 $, @aziza 10 $». Jarimalar o'chiq — «штраф» so'zi yo'q."""
        from . import fines
        from .attendance import break_until
        name = f["name"] if f else ""
        lines = [head(name, "всё ещё без ответа")]
        lines += [link(message_link(a["chat_id"], a["wait_msg_id"] or a["topic_id"], a["topic_id"])) for a in rows]
        day = self.day_of(now)
        due = []
        if fines.on(self.db, "delay"):
            for p in people:
                if break_until(self.db, p["id"], now) or fines.episode_of(self.db, p["id"], anchor, self.episode_sec()):
                    continue                               # tanaffusda / o'sha zaderjka davomi — jarima yo'q
                n, usd = fines.next_amount(self.db, p["id"], "delay", day)
                due.append((p, n, usd))
        warn = f"⏰ <b>Ответьте в течение {grace // 60} мин"
        paid = [(p, usd) for p, _n, usd in due if usd > 0]
        if paid and len({usd for _p, usd in paid}) == 1:
            warn += f" — иначе штраф {fines.money(paid[0][1])} $" + (" (каждому)" if len(paid) > 1 else "") + "</b>"
        elif paid:
            warn += " — иначе штраф: " + ", ".join(f"{esc(P.mention(p))} {fines.money(usd)} $" for p, usd in paid) + "</b>"
        elif due:
            warn += f"</b> — иначе задержка ({fines.ordinal(due[0][1], 'delay')})"
        else:
            warn += "</b>"
        lines.append(warn)
        lines += self.break_lines(people, now)
        lines.append(tag(people))
        return "\n".join(x for x in lines if x)

    async def _remind_alerts(self, now: int) -> int:
        """«задержка» N daqiqa (yoki ish kuni tugaguncha) javobsiz — o'sha xabarga javob qilib eslatma, RD ning bugungi
        xodimi belgilanadi. Muhlatda ham javob bo'lmasa — 1 ta zaderjka: kunlik zinapoya bo'yicha jarima (💸). Bir vaqtda
        va keyingi 30 daqiqada kechikkanlar — o'sha 1 ta. Eslatma paytida tanaffusda bo'lgan xodimga — jarima yo'q."""
        on, after, grace = self.alert_remind_rules()
        if not on:
            return 0
        ws, we = self.work_window()
        work = is_work_time(now, self.tz, ws, we)
        end_ts = self._last_work_end(now)
        eod = not work and end_ts <= now <= end_ts + 3 * 3600   # ish kuni hozirgina tugadi — eslatma vaqti kelsa
        changed = 0
        if work or eod:
            for g in self.db.all("SELECT group_chat_id gid, group_msg_id mid, folder_id, MIN(created_ts) created "
                                 "FROM alerts WHERE status='open' AND group_msg_id IS NOT NULL AND created_ts>=? "
                                 "GROUP BY group_chat_id, group_msg_id", (now - 86400,)):
                if self.db.one("SELECT 1 FROM alert_reminders WHERE gid=? AND mid=?", (g["gid"], g["mid"])):
                    continue
                if now < g["created"] + after:            # kun oxirida ham odatdagi vaqt (egasi, 2026-10-30)
                    continue
                rows = await self._unanswered(g["gid"], g["mid"])
                if not rows:
                    continue
                f = P.folder(self.db, g["folder_id"])
                people = self.workers(g["folder_id"], now) if f else []
                rgid = rmid = None
                try:
                    rgid, rmid = await self.notifier.send_group(
                        self._remind_text(f, rows, people, grace, now, g["created"]), reply_to=g["mid"])
                except Exception as exc:
                    log.warning("Eslatma yuborilmadi: %s", exc)
                self.db.run("INSERT OR IGNORE INTO alert_reminders(gid, mid, folder_id, reminded_ts, rgid, rmid, "
                            "deadline) VALUES(?,?,?,?,?,?,?)", (g["gid"], g["mid"], g["folder_id"], now, rgid, rmid,
                                                                 now + grace))
                changed += 1
        for r in self.db.all("SELECT * FROM alert_reminders WHERE status='open'"):
            rows = await self._unanswered(r["gid"], r["mid"])
            f = P.folder(self.db, r["folder_id"]) if r["folder_id"] else None
            if not rows:
                self.db.run("UPDATE alert_reminders SET status='ok', ended_ts=? WHERE gid=? AND mid=?",
                            (now, r["gid"], r["mid"]))
                if r["rmid"]:
                    from . import fines
                    ok = "✅ ответили — без штрафа" if fines.on(self.db, "delay") else "✅ ответили"
                    try:
                        await self.notifier.edit_group(r["rgid"], r["rmid"], "\n".join([head(f["name"] if f else "",
                                                                                              "напоминание"), ok]))
                    except Exception as exc:
                        log.info("Eslatma tahrirlanmadi: %s", exc)
                    from .tidy import remember
                    remember(self.db, r["rgid"], r["rmid"], "info", now)   # 🧹 jarimasiz — keyin o'chadi
                changed += 1
                continue
            if now < r["deadline"]:
                continue
            await self._missed(r, f, now)
            changed += 1
        return changed

    async def _missed(self, r, f, now: int) -> None:
        """Eslatmadan keyin ham javob yo'q: RD ning o'sha kungi xodimiga 1 ta zaderjka (zinapoya bo'yicha jarima)."""
        from . import fines
        from .attendance import break_until
        fday = local_date(r["reminded_ts"], self.tz)
        people = self.workers(r["folder_id"], r["reminded_ts"]) if f else []
        anchor = self._group_anchor(r["gid"], r["mid"])
        lines, money_fine, struck = [], False, False
        if fines.on(self.db, "delay"):
            for p in people:
                if break_until(self.db, p["id"], r["reminded_ts"]):
                    lines.append(f"☕ {esc(P.mention(p))} на перерыве — без штрафа")
                    continue
                ep = fines.episode_of(self.db, p["id"], anchor, self.episode_sec())
                if ep is not None:
                    lines.append(f"⏰ {esc(P.mention(p))} — не ответили после напоминания · та же задержка, что в "
                                 f"{self.hm(ep['ts'])} — без нового штрафа")
                    continue
                res = fines.strike(self.db, p["id"], "delay", fday, anchor, r["folder_id"], ref=f"{r['gid']}:{r['mid']}",
                                   note=f"{f['name'] if f else ''}: задержка без ответа после напоминания")
                if res is None:
                    continue
                struck = True
                money_fine = money_fine or res["usd"] > 0
                lines.append(fines.delay_line(p, res))
        self.db.run("UPDATE alert_reminders SET status=?, ended_ts=? WHERE gid=? AND mid=?",
                    ("fined" if struck else "missed", now, r["gid"], r["mid"]))
        if not r["rmid"]:
            return
        name = f["name"] if f else ""
        text = "\n".join([head(name)] + lines) if lines else \
            "\n".join([head(name, "не ответили после напоминания"), tag(people)])
        try:
            await self.notifier.edit_group(r["rgid"], r["rmid"], text)
        except Exception as exc:
            log.info("Eslatma tahrirlanmadi: %s", exc)
        if not money_fine:
            from .tidy import remember
            remember(self.db, r["rgid"], r["rmid"], "info", now)   # jarimasiz — 🧹 keyin o'chadi

    def fine_people(self, fid: int, day) -> list:
        """Shu kuni RD da ishlagan xodim(lar) — 📅 Bugun kim qayerda bo'yicha (ball va hisobotlar uchun)."""
        return R.workers(self.db, fid, day)


def plural_leads(n: int) -> str:
    n = int(n)
    if n % 10 == 1 and n % 100 != 11:
        w = "лид"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        w = "лида"
    else:
        w = "лидов"
    return f"{n} {w}"
