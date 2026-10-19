"""Zaderjka va stavka qoidalari — botning yuragi. Telegram'ga bog'liq emas, alohida sinaladi.

Qoidalar (egasi bilan kelishilgan):
* Mijoz xabarlari FAQAT vositachi bot orqali keladi: bot (User.bot) yozgan = mijoz; har qanday odam yozgan = javob.
  Push akkauntlarimiz xabarlari hisobga olinmaydi.
* Yangi lid (yangi topik) → stavka. Stavka = N ta dumaloq video, HAR video bilan vositachi bot darrov matn ham yozadi
  (2026-10-19 jurnalida topilgan xato: 3-videodan keyingi matn mijoz xabari deb olingan edi). Stavka N-video va uning
  matni bilan tugaydi. Stavka paytida hech kimning xabari zaderjka hisoblanmaydi.
* Video belgilangan vaqtda kelmasa — «Проёб»ga bir marta «ставка» eslatmasi (zaderjka emas).
* Zaderjka: mijozning BIRINCHI javobsiz xabaridan, faqat ish vaqtida (va papkaning hamma xodimi tanaffusda bo'lmasa),
  limitdan oshsa «Проёб»ga bir marta «задержка». Javob kelganda ✅. Jarima = limitdan oshgan daqiqa × papka narxi ($),
  papkadagi har bir xodimga (o'sha kuni dam olayotganlardan tashqari).
* Hamma xabarlar nit ichida id tartibida bir marta ishlanadi (jonli va qayta ulanishdagi xabarlar bitta yo'ldan).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from . import people as P
from .db import Database
from .links import message_link
from .timeutil import minutes_up, parse_hhmm, work_seconds, local_date, is_work_time

log = logging.getLogger("rules")

MAX_LINKS = 10                 # bitta «задержка» xabarida eng ko'pi bilan nechta havola
INCIDENT_FRESH = 3600          # «holat» uchun oxirgi shuncha soniyadagi «задержка»lar sanaladi

# qaror kodlari (jurnal va «Lidni tekshirish» ekrani uchun)
DECISIONS = ("dup", "service", "ours", "excluded", "before", "stavka_skip", "stavka_bet", "bet_text", "stavka_end",
             "auto_bet", "wait", "wait_more", "reply", "staff", "alert")


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
        self.reload()

    # ------------------------------------------------------------ keshlar
    def reload(self) -> None:
        rows = self.db.all("SELECT chat_id, folder_id, is_forum FROM chats")
        self.chat_folder = {r["chat_id"]: r["folder_id"] for r in rows}
        self.forums = {r["chat_id"] for r in rows if r["is_forum"]}

    def is_monitored(self, chat_id: int) -> bool:
        return chat_id in self.chat_folder

    def stavka_limits(self) -> tuple[int, int, int, int]:
        """(nechta video, eslatma soniyada, eng ko'p davom soniyada, video matni oynasi soniyada)."""
        need = max(1, self.db.get_int("stavka_count", 3))
        remind = max(1, self.db.get_int("stavka_next", 20)) * 60
        cap = max(remind, self.db.get_int("stavka_cap", 180) * 60)
        window = max(10, self.db.get_int("bet_text_seconds", 120))
        return need, remind, cap, window

    def remind_rules(self) -> tuple[int, int, int]:
        """(birinchi stavka uchun soniya, keyingilari uchun soniya, bitta lidga eng ko'p eslatma)."""
        return (max(1, self.db.get_int("stavka_first", 20)) * 60, max(1, self.db.get_int("stavka_next", 20)) * 60,
                max(0, self.db.get_int("stavka_max_remind", 3)))

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

    async def _decide(self, th, m: Msg) -> str:
        c, t = m.chat_id, m.topic_id
        if m.who == "service":
            return "service"
        if m.who == "ours":
            return "ours"
        if m.who == "client":
            self._count_lead(th, m)

        # ── stavka (yangi lid): video + uning matni, N marta
        if th["stavka"] == "on" and m.who == "staff":
            self._set(c, t, last_staff_ts=max(m.ts, th["last_staff_ts"] or 0))
        if th["stavka"] == "on":
            need, _remind, cap, window = self.stavka_limits()
            bets = th["bets"]
            if m.ts > th["stavka_from"] + cap:
                self._finish_stavka(c, t, th["stavka_from"] + cap, "cap")
            elif bets >= need and th["bet_text_wait"] and m.ts - (th["bet_last_ts"] or 0) > window:
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
            if m.ts < self.db.get_int("delay_from"):
                return "before"
            ws, we = self.work_window()
            if not is_work_time(m.ts, self.tz, ws, we):
                return "night"                             # ish vaqtidan tashqari — zaderjka hisoblanmaydi
            if label_excluded(self.label(c, t), skip_list(self.db)):
                return "excluded"
            if th["wait_since"] is None:
                self._set(c, t, wait_since=m.ts, wait_msg_id=m.msg_id)
                return "wait"
            return "wait_more"

        # odam (xodim) yozdi
        self._set(c, t, last_staff_ts=max(m.ts, th["last_staff_ts"] or 0))
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
        fid = self.chat_folder.get(c)
        waited = self.elapsed(fid, th["wait_since"], ts) if fid else 0
        self.db.run("INSERT INTO replies(chat_id, topic_id, folder_id, staff_id, wait_since, reply_ts, work_seconds) "
                    "VALUES(?,?,?,?,?,?,?)", (c, t, fid or 0, staff_id, th["wait_since"], ts, waited))
        self._set(c, t, wait_since=None, wait_msg_id=None, alert_id=None)
        if th["alert_id"]:
            await self._close_alert(th["alert_id"], ts, waited, staff_id, by_button)

    async def _close_alert(self, alert_id: int, ts: int, waited: int, staff_id: int | None,
                           by_button: str | None) -> None:
        """Havola yopildi (javob yoki «✅ Выполнено»). Jarima bu yerda emas — «holat» bo'yicha (_incidents)."""
        a = self.db.one("SELECT * FROM alerts WHERE id=?", (alert_id,))
        if a is None or a["status"] != "open":
            return
        status = "done" if by_button else "answered"
        who = by_button or self._staff_name(staff_id)
        self.db.run("UPDATE alerts SET status=?, closed_ts=?, closed_by=?, waited_min=? WHERE id=?",
                    (status, ts, who, minutes_up(waited), alert_id))
        if a["group_msg_id"]:
            await self.render_alert_message(a["group_chat_id"], a["group_msg_id"])

    def _staff_name(self, uid: int | None) -> str:
        if uid is None:
            return "менеджер"
        p = P.by_tg(self.db, uid)
        if p is not None:
            return P.mention(p)
        h = self.db.one("SELECT name FROM known_humans WHERE user_id=?", (uid,))
        return h["name"] if h and h["name"] else "менеджер"

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
        rows = self.db.all("SELECT * FROM alerts WHERE group_chat_id=? AND group_msg_id=? ORDER BY id", (gid, mid))
        return self._compose(rows)

    def _compose(self, rows) -> tuple[str, bool]:
        if not rows:
            return "", True
        f = P.folder(self.db, rows[0]["folder_id"])
        lines = []
        for r in rows:
            link = message_link(r["chat_id"], r["wait_msg_id"] or r["topic_id"], r["topic_id"])
            lines.append(link if r["status"] == "open" else f"✅ {link}")
        mentions = " ".join(P.mention(p) for p in P.folder_people(self.db, f["id"])) if f else ""
        lines.append(f"{mentions} {f['name'] if f else ''} задержка".strip())
        closed = all(r["status"] != "open" for r in rows)
        if closed:
            whos = []
            for r in rows:
                if r["closed_by"] and r["closed_by"] not in whos:
                    whos.append(r["closed_by"])
            lines.append("✅ Выполнено" + (f" — {', '.join(whos)}" if whos else ""))
        return "\n".join(lines), closed

    async def render_alert_message(self, gid: int, mid: int) -> None:
        text, closed = self.alert_message_text(gid, mid)
        if not text:
            return
        first = self.db.scalar("SELECT MIN(id) FROM alerts WHERE group_chat_id=? AND group_msg_id=?", (gid, mid))
        try:
            await self.notifier.edit_group(gid, mid, text, done_button=None if closed else first)
        except Exception as exc:
            log.info("Alert tahrirlanmadi: %s", exc)

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
        out["incidents"] = await self._incidents(now)
        return out

    def _stavka_timeouts(self, now: int) -> int:
        need, _remind, cap, window = self.stavka_limits()
        done = 0
        for th in self.db.all("SELECT * FROM threads WHERE stavka='on'"):
            if now > th["stavka_from"] + cap:
                self._finish_stavka(th["chat_id"], th["topic_id"], th["stavka_from"] + cap, "cap")
                done += 1
            elif th["bets"] >= need and (not th["bet_text_wait"] or now - (th["bet_last_ts"] or 0) > window):
                end = (th["bet_last_ts"] or now) + (window if th["bet_text_wait"] else 0)
                self._finish_stavka(th["chat_id"], th["topic_id"], min(end, now), "timer")
                done += 1
        return done

    async def _stavka_reminders(self, now: int) -> int:
        """«ставка»: yangi chatdan keyin birinchi stavka N daqiqada, keyingisi oldingisidan (yoki eslatmadan)
        M daqiqada kelmasa — eslatma. Bitta lidga ko'pi bilan K marta. Faqat ish vaqtida."""
        need, _next, cap, _window = self.stavka_limits()
        first, nxt, max_n = self.remind_rules()
        ws, we = self.work_window()
        if not max_n or not is_work_time(now, self.tz, ws, we):
            return 0
        by_folder: dict[int, list] = {}
        for th in self.db.all("SELECT * FROM threads WHERE stavka='on' AND stavka_reminded<? AND bets<?",
                              (max_n, need)):
            fid = self.chat_folder.get(th["chat_id"])
            if fid is None:
                continue
            anchor = max(th["stavka_from"] or 0, th["bet_last_ts"] or 0, th["stavka_remind_ts"] or 0)
            gap = first if (not th["bets"] and not th["stavka_reminded"]) else nxt
            if now >= anchor + gap:
                by_folder.setdefault(fid, []).append(th)
        sent = 0
        for fid, items in by_folder.items():
            f = P.folder(self.db, fid)
            mentions = " ".join(P.mention(p) for p in P.folder_people(self.db, fid))
            links = [message_link(th["chat_id"], th["seen_msg_id"] or th["topic_id"], th["topic_id"]) for th in items]
            text = "\n".join(links + [f"{mentions} {f['name'] if f else ''} ставка".strip()])
            try:
                await self.notifier.send_group(text)
            except Exception as exc:
                log.warning("«ставка» yuborilmadi: %s", exc)
                continue
            for th in items:
                self._set(th["chat_id"], th["topic_id"], stavka_reminded=th["stavka_reminded"] + 1,
                          stavka_remind_ts=now)
                sent += 1
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
            mentions = " ".join(P.mention(p) for p in P.folder_people(self.db, fid))
            for i in range(0, len(items), MAX_LINKS):
                part = items[i:i + MAX_LINKS]
                links = [message_link(th["chat_id"], th["wait_msg_id"] or th["topic_id"], th["topic_id"]) for th in part]
                head = " ".join(x for x in ("🌙", mentions, f"{f['name']}:") if x)
                text = "\n".join(links + [f"{head} рабочий день закончился, эти чаты без ответа — доведите работу "
                                           "до конца, чтобы ни один чат не остался без ответа"])
                try:
                    await self.notifier.send_group(text)
                    sent += len(part)
                except Exception as exc:
                    log.warning("Kun oxiri eslatmasi yuborilmadi: %s", exc)
        # ertalab ular uchun zaderjka bo'lmaydi
        self.db.run("UPDATE threads SET wait_since=NULL, wait_msg_id=NULL, alert_id=NULL WHERE wait_since IS NOT NULL")
        return sent

    async def _delays(self, now: int) -> int:
        limit = max(1, self.db.get_int("limit_minutes", 20)) * 60
        folders = {f["id"]: f for f in P.folders(self.db)}
        skip = skip_list(self.db)
        due: dict[int, list] = {}
        for th in self.db.all("SELECT * FROM threads WHERE wait_since IS NOT NULL AND alert_id IS NULL "
                              "ORDER BY wait_since"):
            fid = self.chat_folder.get(th["chat_id"])
            f = folders.get(fid)
            if f is None or not f["delay_on"] or th["stavka"] == "on":
                continue
            if label_excluded(self.label(th["chat_id"], th["topic_id"]), skip):
                self._set(th["chat_id"], th["topic_id"], wait_since=None, wait_msg_id=None)
                continue
            if self.elapsed(fid, th["wait_since"], now) >= limit:
                due.setdefault(fid, []).append(th)
        sent = 0
        for fid, items in due.items():
            for i in range(0, len(items), MAX_LINKS):
                sent += await self._send_alert(items[i:i + MAX_LINKS], folders[fid], now)
        return sent

    async def _send_alert(self, items: list, f, now: int) -> int:
        """Papka bo'yicha bitta «задержка» xabari (bir nechta havola). -> nechta nit."""
        ids = []
        for th in items:
            cur = self.db.run("INSERT INTO alerts(chat_id, topic_id, folder_id, wait_since, wait_msg_id, created_ts) "
                              "VALUES(?,?,?,?,?,?)", (th["chat_id"], th["topic_id"], f["id"], th["wait_since"],
                                                      th["wait_msg_id"], now))
            ids.append(int(cur.lastrowid))
        rows = self.db.all("SELECT * FROM alerts WHERE id IN (%s) ORDER BY id" % ",".join("?" * len(ids)), ids)
        text, _ = self._compose(rows)
        try:
            gid, mid = await self.notifier.send_group(text, done_button=ids[0])
        except Exception as exc:
            self.db.run("DELETE FROM alerts WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
            log.warning("«задержка» yuborilmadi: %s", exc)
            return 0
        self.db.run("UPDATE alerts SET group_chat_id=?, group_msg_id=? WHERE id IN (%s)" % ",".join("?" * len(ids)),
                    [gid, mid] + ids)
        for th, aid in zip(items, ids):
            self._set(th["chat_id"], th["topic_id"], alert_id=aid)
            self.db.run("INSERT INTO journal(at, ts, chat_id, topic_id, msg_id, sender_id, who, kind, source, "
                        "decision) VALUES(?,?,?,?,?,?,?,?,?,?)", (now, th["wait_since"], th["chat_id"],
                                                                   th["topic_id"], th["wait_msg_id"], None, "", "",
                                                                   "timer", "alert"))
        return len(items)

    # ------------------------------------------------------------ jarima: «holat» (papkada ko'p lid javobsiz)
    def fine_amount(self, f) -> float:
        """Papkaning zaderjka jarimasi: alohida summa (>0), o'chiq (<0) yoki umumiy summa."""
        own = float(f["fine_usd"] or 0) if f is not None else 0.0
        if own < 0:
            return 0.0
        return own if own > 0 else max(0.0, self.db.get_float("fine_amount"))

    def fine_rules(self) -> tuple[int, int, int]:
        """(nechta lid birdaniga, kuniga nechta kechirim, javob uchun necha soniya)."""
        return (max(1, self.db.get_int("fine_min_leads", 3)), max(0, self.db.get_int("fine_forgive", 2)),
                max(0, self.db.get_int("fine_grace", 3)) * 60)

    async def _incidents(self, now: int) -> int:
        """Papkada bir vaqtda N+ lid javobsiz → «holat». Kuniga birinchi K tasi — ogohlantirish (jarimasiz).
        Keyingisi: ogohlantirishdan G daqiqada javob bo'lmasa — bir martalik jarima papkaning har xodimiga.

        Har bir «задержка» havolasi faqat BITTA holatga kiradi; oxirgi 1 soatdagi havolalar sanaladi (kunlab javobsiz
        qolib ketgan eski havolalar keyingi holatlarni to'sib qo'ymaydi va qayta sanalmaydi)."""
        n_min, forgive, grace = self.fine_rules()
        changed = 0
        for f in P.folders(self.db):
            active = self.db.one("SELECT * FROM incidents WHERE folder_id=? AND ended_ts IS NULL ORDER BY id DESC "
                                 "LIMIT 1", (f["id"],))
            free = [r["id"] for r in self.db.all(
                "SELECT id FROM alerts WHERE folder_id=? AND status='open' AND created_ts>=? AND id NOT IN "
                "(SELECT alert_id FROM incident_alerts)", (f["id"], now - INCIDENT_FRESH))]
            if active is None:
                episode = max(0, self.db.get_int("fine_episode", 30)) * 60
                recent = self.db.one("SELECT id FROM incidents WHERE folder_id=? AND started_ts>=? ORDER BY id DESC "
                                     "LIMIT 1", (f["id"], now - episode)) if episode else None
                if recent is not None:                    # o'sha «yo'qlik» davomi — yangi holat emas
                    self.db.many("INSERT OR IGNORE INTO incident_alerts(incident_id, alert_id) VALUES(?,?)",
                                 [(recent["id"], a) for a in free])
                elif (len(free) >= n_min and f["delay_on"] and self.fine_amount(f) > 0 and self.db.flag("fines_enabled")
                        and self.db.flag("delay_enabled")):
                    await self._start_incident(f, free, now, forgive, grace)
                    changed += 1
                continue
            for aid in free:                              # kutish paytida kechikkanlar ham shu holatga kiradi
                self.db.run("INSERT OR IGNORE INTO incident_alerts(incident_id, alert_id) VALUES(?,?)",
                            (active["id"], aid))
            still = self.db.scalar("SELECT COUNT(*) FROM incident_alerts ia JOIN alerts a ON a.id=ia.alert_id "
                                   "WHERE ia.incident_id=? AND a.status='open'", (active["id"],))
            if still == 0:
                self.db.run("UPDATE incidents SET status='ok', ended_ts=? WHERE id=?", (now, active["id"]))
                await self._render_incident(active["id"])
                changed += 1
            elif now >= (active["deadline"] or now):
                await self._fine_incident(active, f, now)
                changed += 1
        return changed

    async def _start_incident(self, f, open_ids: list, now: int, forgive: int, grace: int) -> None:
        day = local_date(now, self.tz).isoformat()
        seq = self.db.scalar("SELECT COUNT(*) FROM incidents WHERE folder_id=? AND day=?", (f["id"], day)) + 1
        status = "warn" if seq <= forgive else "grace"
        iid = int(self.db.run("INSERT INTO incidents(folder_id, day, seq, started_ts, n_leads, status, deadline, "
                              "fine_usd, ended_ts) VALUES(?,?,?,?,?,?,?,?,?)",
                              (f["id"], day, seq, now, len(open_ids), status, now + grace if status == "grace" else None,
                               self.fine_amount(f), now if status == "warn" else None)).lastrowid)
        self.db.many("INSERT OR IGNORE INTO incident_alerts(incident_id, alert_id) VALUES(?,?)",
                     [(iid, a) for a in open_ids])
        try:
            gid, mid = await self.notifier.send_group(self.incident_text(iid))
            self.db.run("UPDATE incidents SET group_chat_id=?, group_msg_id=? WHERE id=?", (gid, mid, iid))
        except Exception as exc:
            log.warning("Holat xabari yuborilmadi: %s", exc)
        log.info("Holat: %s #%s (%s lid) — %s", f["name"], seq, len(open_ids), status)

    async def _fine_incident(self, inc, f, now: int) -> None:
        amount = float(inc["fine_usd"] or 0)
        if amount <= 0 or not self.db.flag("fines_enabled"):
            self.db.run("UPDATE incidents SET status='ok', ended_ts=? WHERE id=?", (now, inc["id"]))
            await self._render_incident(inc["id"])
            return
        self.db.run("UPDATE incidents SET status='fined', ended_ts=? WHERE id=?", (now, inc["id"]))
        day = local_date(now, self.tz)
        from .kassa import add_adj
        for p in P.folder_people(self.db, f["id"]):
            if not p["active"] or P.is_day_off(p, day.weekday()):
                continue
            add_adj(self.db, p["id"], "fine", amount, day.isoformat(), source="delay", ref_id=inc["id"],
                    note=f"{f['name']}: {plural_leads(inc['n_leads'])} без ответа")
        await self._render_incident(inc["id"])

    def incident_text(self, iid: int) -> str:
        """«Проёб» uchun (ruscha)."""
        inc = self.db.one("SELECT * FROM incidents WHERE id=?", (iid,))
        f = P.folder(self.db, inc["folder_id"])
        name = f["name"] if f else ""
        mentions = " ".join(P.mention(p) for p in P.folder_people(self.db, inc["folder_id"])) if f else ""
        _n, forgive, grace = self.fine_rules()
        leads = plural_leads(inc["n_leads"])
        amount = f"{inc['fine_usd']:g} $"
        if inc["status"] == "warn":
            return (f"⚠️ {mentions} {name}: {leads} без ответа.\n"
                    f"Предупреждение {inc['seq']} из {forgive} за сегодня — без штрафа.").strip()
        if inc["status"] == "grace":
            return (f"⏳ {mentions} {name}: {leads} без ответа.\n"
                    f"Ответьте за {grace // 60} мин — иначе штраф {amount} каждому.").strip()
        if inc["status"] == "fined":
            return (f"💸 {mentions} {name}: штраф {amount} каждому.\n"
                    f"{leads} без ответа, не ответили за {grace // 60} мин.").strip()
        return f"✅ {name}: ответили вовремя — без штрафа."

    async def _render_incident(self, iid: int) -> None:
        inc = self.db.one("SELECT * FROM incidents WHERE id=?", (iid,))
        if inc is None or not inc["group_msg_id"]:
            return
        try:
            await self.notifier.edit_group(inc["group_chat_id"], inc["group_msg_id"], self.incident_text(iid))
        except Exception as exc:
            log.info("Holat xabari tahrirlanmadi: %s", exc)


def plural_leads(n: int) -> str:
    n = int(n)
    if n % 10 == 1 and n % 100 != 11:
        w = "лид"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        w = "лида"
    else:
        w = "лидов"
    return f"{n} {w}"
