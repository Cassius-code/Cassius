"""Asosiy akkaunt (Telethon) — botning «ko'zi». Xabardan faqat metama'lumot olinadi: chat, topik, id, vaqt,
yuboruvchi (bot/odam), dumaloq videomi. Matn o'qilmaydi va saqlanmaydi.

Jonli xabarlar va qayta ulanishda o'tkazib yuborilganlar BITTA yo'ldan ishlanadi (Tracker.handle), nit ichida id
tartibida. Yangi topik birinchi marta ko'rilganda uning boshidan xabarlari olinadi — stavka to'g'ri sanaladi.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from . import people as P
from .rules import Msg, Tracker
from .tgclient import TgAccount
from .tgsend import PushSender

log = logging.getLogger("userbot")

TOPIC_FETCH_LIMIT = 300        # yangi topik: boshidan nechta xabar olinadi
OLD_THREAD_TAIL = 15           # eski (o'rnatishdan oldingi) nit birinchi ko'rilganda: oxirgi nechta xabar
SYNC_EVERY = 600               # papka/topik sinxroni va tekshiruv har necha soniyada
WATCH_EVERY = 2                # ish vaqtida: guruhlarda yangi xabar bormi — har necha soniyada tekshiriladi
# Vositachi botning o'z menyusi: «Статус: 🔥 Новый …» (/status paneli), «✅Установлен: 💊 Мариновка». Bu mijoz xabari
# emas. Faqat xabar boshidagi bir necha belgiga qaraladi — matn o'qilmaydi va saqlanmaydi.
BOT_UI_RE = re.compile(r"^\W*((статус|установлен|status)\s*:|реквизиты\s+отправлены)", re.IGNORECASE)
CMD_WINDOW = 300               # xodim /buyruq yozgandan keyin botning tugmali javobi — menyu (5 daqiqagacha)
CMD_ECHO = 10                  # xodim /buyruq yozgandan keyin shu soniya ichida bot yozgani — buyruq javobi, mijoz emas
DEEP_SCAN_V = "2"              # Push bazasini yig'ish qoidasi (o'zgarsa — baza bir marta qaytadan yig'iladi)


def thread_of(m, is_forum: bool) -> int:
    rt = getattr(m, "reply_to", None)
    if rt is not None and getattr(rt, "forum_topic", False):
        return int(getattr(rt, "reply_to_top_id", None) or getattr(rt, "reply_to_msg_id", None) or 1)
    return 1 if is_forum else 0


def _unix(d) -> int | None:
    if d is None:
        return None
    if hasattr(d, "timestamp"):
        return int(d.timestamp())
    try:
        return int(d)
    except (TypeError, ValueError):
        return None


def username_of(user) -> str:
    """Telegram @username (Fragment'dan olingan «kolleksiya» nomlari ham — ular usernames ro'yxatida)."""
    u = getattr(user, "username", None)
    if u:
        return str(u)
    for x in getattr(user, "usernames", None) or []:
        if getattr(x, "active", True) and getattr(x, "username", None):
            return str(x.username)
    return ""


def folder_key(name: str) -> str:
    """Papka nomini solishtirish: katta-kichik harf, bo'sh joy va emoji farq qilmaydi («Rd3.1» = «RD 3.1 🔥»)."""
    import re
    return re.sub(r"[^\w.]+", "", (name or "").casefold())


class Userbot(TgAccount, PushSender):
    def __init__(self, cfg, db, tracker: Tracker, notifier, tz):
        super().__init__(cfg, db, notifier)
        self.tracker = tracker
        self.tz = tz
        self._lock = asyncio.Lock()
        self.last_sync = 0.0
        self.last_event = 0.0
        self.missing_folders: list[str] = []
        self.tg_folders: list[str] = []          # asosiy akkauntdagi Telegram papkalari (nomlari)
        self._push_ids: set[int] = set()
        self._bots: set[int] = set()
        self._humans: dict[int, tuple] = {}        # odam -> (@username, ism): xodimga bog'lash bir marta
        self.deep_running = False                  # Push bazasini to'liq tekshirish ketyapti
        self._deep_task = None
        self.tick = 1                              # kuzatuv uchun tez-tez uyg'onadi
        self._watch_pause = 0.0                    # Telegram «sekinlang» (FloodWait) desa — shu vaqtgacha kutish
        self._tops: dict[int, int] = {}            # chat -> oxirgi ko'rilgan xabar id (kuzatuv)
        self._live_ids: dict[int, set] = {}        # chat -> jonli kelgan xabar raqamlari (tushib qolganini topish uchun)
        self._hist: dict[int, int] = {}            # chat -> shu raqamgacha hamma xabar ishlangan (jonli yoki tarixdan)
        self._cmd_ts: dict[tuple, float] = {}      # (chat, topik) -> xodim oxirgi /buyruq yozgan vaqt
        self._last_watch = 0.0
        self._sync_task = None                     # papka/topik sinxroni fonda (kuzatuvni ushlab turmaydi)
        self.watch_found = 0                       # kuzatuv topgan (jonli kelmay qolgan) xabarlar
        self.flood_threshold = 10                  # Telegram 10 s dan ko'p kuttirsa — so'rov kutmasdan xato qaytaradi
        self._resolve_pause = 0.0                  # @username so'rovlari shu vaqtgacha to'xtatilgan (FloodWait)
        self.reload_ids()

    def title(self) -> str:
        return "Asosiy akkaunt"

    def session(self) -> str:
        return self.db.get("userbot_session")

    async def set_session(self, session: str) -> None:
        self.db.set("userbot_session", session)
        self.state = "connecting"
        self.wake()

    async def logout(self) -> None:
        self.db.set("userbot_session", "")
        self.state = "no_session"
        self.wake()

    def reload_ids(self) -> None:
        self._push_ids = {r["user_id"] for r in self.db.all("SELECT user_id FROM accounts WHERE user_id IS NOT NULL")}
        self._bots = {r["user_id"] for r in self.db.all("SELECT user_id FROM known_bots")}

    # ------------------------------------------------------------ ulanish
    async def on_online(self, client) -> None:
        from telethon import events
        client.add_event_handler(self._on_event, events.NewMessage())
        self.tracker.main_id = self.me_id
        log.info("Asosiy akkaunt ulandi: %s", self.me_label)
        self._start_sync()

    def _start_sync(self) -> None:
        if self._sync_task is not None and not self._sync_task.done():
            return
        self.last_sync = time.time()
        self._sync_task = asyncio.create_task(self._sync_bg())

    async def _sync_bg(self) -> None:
        try:
            await self.sync_all()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Sinxron xatosi")

    async def periodic(self, client) -> None:
        """Har tick (5 s): kuzatuv darhol; uzoq sinxron — fonda (kuzatuv va «выполнено» kutib qolmasin)."""
        if time.time() - self.last_sync >= SYNC_EVERY:
            self._start_sync()
        await self.watch(client)

    # ------------------------------------------------------------ ish vaqtida kuzatuv
    def in_work_time(self, now: float | None = None) -> bool:
        """Ish vaqti (5 daqiqa oldin va keyin bilan)."""
        from datetime import datetime
        t = datetime.fromtimestamp(now or time.time(), self.tz)
        ws, we = self.tracker.work_window()
        cur = t.hour * 60 + t.minute
        a, b = (ws.hour * 60 + ws.minute - 5) % 1440, (we.hour * 60 + we.minute + 5) % 1440
        return a <= cur <= b if a <= b else (cur >= a or cur <= b)

    async def watch(self, client, now: float | None = None) -> None:
        """Ish vaqtida har WATCH_EVERY soniyada guruhlarning oxirgi xabari tekshiriladi (akkaunt «online» qilinmaydi).
        Telegram jonli xabarni yetkazmay qolsa ham, u shu yerda topilib, o'z vaqti bilan ishlanadi (zaderjka aniq)."""
        now = now or time.time()
        if not (self.in_work_time(now) and self.db.flag("bot_enabled")):
            return
        if now - self._last_watch < WATCH_EVERY or now < self._watch_pause:
            return
        self._last_watch = now
        try:
            await self.poll_chats(client)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            wait = getattr(exc, "seconds", None)
            if wait:                                       # FloodWait: Telegram so'rovni kamaytirishni so'radi
                self._watch_pause = now + int(wait)
                log.warning("Kuzatuv: Telegram %s s kutishni so'radi", wait)
            else:
                log.info("Kuzatuv: %s", type(exc).__name__)

    async def poll_chats(self, client) -> int:
        """Bitta so'rov bilan hamma guruhning oxirgi xabar raqami. Guruhda xabar raqamlari ketma-ket: oxirgi
        tekshirilgandan beri jonli KELMAGAN raqam bo'lsa — faqat o'sha oraliq Telegram'dan olinib, tartib bilan
        ishlanadi (boshqa topikka jonli xabar kelgan bo'lsa ham, tushib qolgani topiladi)."""
        from telethon import utils
        from telethon.tl.functions.messages import GetPeerDialogsRequest
        from telethon.tl.types import InputDialogPeer
        chats = list(self.tracker.chat_folder)
        peers = []
        for cid in chats:
            try:
                peers.append((cid, await client.get_input_entity(cid)))
            except Exception:
                continue
        found = 0
        for i in range(0, len(peers), 50):
            part = peers[i:i + 50]
            res = await client(GetPeerDialogsRequest(peers=[InputDialogPeer(peer=p) for _c, p in part]))
            tops = {}
            for d in getattr(res, "dialogs", []):
                try:
                    tops[int(utils.get_peer_id(d.peer))] = int(d.top_message or 0)
                except Exception:
                    continue
            for cid, p in part:
                top = tops.get(cid, 0)
                if not top:
                    continue
                self._tops[cid] = max(top, self._tops.get(cid, 0))
                done = self._hist.get(cid)
                if done is None:
                    self._hist[cid] = top                      # birinchi marta: shu joydan (eskisi — catch_up)
                    continue
                if top <= done:
                    continue
                live = self._live_ids.get(cid, set())
                if any(x not in live for x in range(done + 1, top + 1)):
                    found += await self._poll_gap(client, cid, p, done, top)
                self._hist[cid] = top
                self._live_ids[cid] = {x for x in live if x > top}
        self.watch_found += found
        if found:
            log.info("Kuzatuv: jonli kelmagan %s ta xabar topildi va ishlandi", found)
        return found

    async def _poll_gap(self, client, chat_id: int, peer, lo: int, hi: int) -> int:
        """lo dan keyin hi gacha (shu jumladan) jonli kelmagan xabarlar: olib, eski → yangi tartibda ishlash."""
        live = self._live_ids.get(chat_id, set())
        msgs = []
        async for m in client.iter_messages(peer, min_id=lo, max_id=hi + 1, reverse=True, limit=400):
            if int(m.id) not in live:
                msgs.append(m)
        forum = chat_id in self.tracker.forums
        n = 0
        for m in msgs:
            topic = thread_of(m, forum)
            if forum and topic == 1:
                continue
            async with self._lock:
                if int(m.id) in self._live_ids.get(chat_id, ()):
                    continue                                     # shu orada jonli kelib ishlandi
                th = self.tracker.thread(chat_id, topic)
                if th is None:
                    await self._first_sight(chat_id, topic, int(m.id), forum)
                    th = self.tracker.thread(chat_id, topic)
                if int(m.id) <= th["seen_msg_id"]:
                    await self._process(m, chat_id, topic, "watch", late=True)
                else:
                    await self._process(m, chat_id, topic, "watch")
                n += 1
        return n

    async def sync_all(self) -> None:
        """Papkalar → xodimlarning ID si → topiklar va o'tkazib yuborilgan xabarlar."""
        self.last_sync = time.time()
        for step in (self.sync_folders, self.resolve_people, self.catch_up):
            try:
                await step()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Sinxron qadami %s xato", step.__name__)
        base = self.db.get("push_base_from") or "2026-08-28"
        if self.client is not None and not self.deep_running and (self.db.get("deep_scan_base") != base or
                                                                    self.db.get("deep_scan_v") != DEEP_SCAN_V):
            self._deep_task = asyncio.create_task(self._deep_bg())    # uzoq ish — sinxronni ushlab turmaydi

    async def _deep_bg(self) -> None:
        try:
            await self.deep_scan()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Push bazasini to'liq tekshirish xatosi")

    # ------------------------------------------------------------ jonli xabar
    async def _on_event(self, event) -> None:
        try:
            chat_id = event.chat_id
            if chat_id is None or not self.tracker.is_monitored(chat_id):
                return
            m = event.message
            self._live_ids.setdefault(chat_id, set()).add(int(m.id))
            forum = chat_id in self.tracker.forums
            if not forum and getattr(getattr(m, "chat", None), "forum", False):
                self.db.run("UPDATE chats SET is_forum=1 WHERE chat_id=?", (chat_id,))
                self.tracker.reload()
                forum = True
            topic = thread_of(m, forum)
            if forum and topic == 1:
                return                                       # «General» — lid emas
            self.last_event = time.time()
            action = getattr(m, "action", None)
            if action is not None and "TopicEdit" in type(action).__name__ and topic > 1:
                asyncio.create_task(self.refresh_topic(chat_id, topic))     # status (🔥/⚡/💊) o'zgardi
            async with self._lock:
                if self.tracker.thread(chat_id, topic) is None:
                    await self._first_sight(chat_id, topic, int(m.id), forum)
                await self._process(m, chat_id, topic, "live")
        except Exception:
            log.exception("Xabarni ishlashda xato (metama'lumot)")

    async def _first_sight(self, chat_id: int, topic: int, msg_id: int, forum: bool) -> None:
        """Nitni birinchi marta ko'rdik: yangi topikmi (stavka) — bilib olamiz va undan oldingi xabarlarini ishlaymiz."""
        created = None
        if forum and topic > 1:
            created = await self._topic_created(chat_id, topic)
            if created is None and 0 < msg_id - topic <= 25:
                created = int(time.time())                 # ma'lumot olinmadi, lekin topikning birinchi xabarlari
                self.db.run("INSERT INTO topics(chat_id, topic_id, created_ts) VALUES(?,?,?) ON CONFLICT(chat_id, "
                            "topic_id) DO UPDATE SET created_ts=COALESCE(topics.created_ts, excluded.created_ts)",
                            (chat_id, topic, created))
        self.tracker.start_thread(chat_id, topic, created)
        th = self.tracker.thread(chat_id, topic)
        if th["stavka"] == "on":
            await self._fetch_and_process(chat_id, topic, min_id=topic if topic > 1 else 0, upto=msg_id - 1,
                                          limit=TOPIC_FETCH_LIMIT)
        else:
            await self._fetch_and_process(chat_id, topic, min_id=0, upto=msg_id - 1, limit=OLD_THREAD_TAIL, tail=True)

    async def _topic_created(self, chat_id: int, topic: int) -> int | None:
        from telethon.tl.functions.channels import GetForumTopicsByIDRequest
        try:
            peer = await self.client.get_input_entity(chat_id)
            res = await self.client(GetForumTopicsByIDRequest(channel=peer, topics=[topic]))
            for t in getattr(res, "topics", []) or []:
                if int(t.id) == topic:
                    await self._store_topics(chat_id, [t])
                    return _unix(getattr(t, "date", None))
        except Exception as exc:
            log.info("Topik ma'lumoti olinmadi %s/%s: %s", chat_id, topic, type(exc).__name__)
        return None

    # ------------------------------------------------------------ xabarni turga ajratish
    async def classify(self, m, chat_id: int, topic: int = 0) -> str:
        if getattr(m, "action", None) is not None:
            return "service"
        if self.db.one("SELECT 1 FROM ignored_msgs WHERE chat_id=? AND msg_id=?", (chat_id, int(m.id))):
            return "ours"
        sid = m.sender_id
        if sid is not None and sid in self._push_ids:
            # papka akkaunti: xodim undan mijozga JAVOB yozadi (jurnal: RD 7 da deyarli hamma javob shundan).
            # Faqat Push yuborgan xabar «biz»; qolgani — xodim javobi.
            return "ours" if self._is_push_message(chat_id, topic, int(m.id)) else "staff"
        if m.out:                                          # asosiy akkauntdan yozilgan — javob,
            if self.db.one("SELECT 1 FROM folders WHERE push_account_id=-1"):   # agar Push o'zi yubormagan bo'lsa
                return "ours" if self._is_push_message(chat_id, topic, int(m.id)) else "staff"
            return "staff"
        is_bot = await self._is_bot(m)
        return "client" if is_bot else "staff"

    def _is_push_message(self, chat_id: int, topic: int, msg_id: int) -> bool:
        """Push yuborgan xabarmi? Yuborilgan bo'lsa — ignored_msgs da; hozir yuborilayotgan bo'lsa (Telegram xabarni
        yuboruvchi qayd etishidan oldin yetkazishi mumkin) — Push yuborayotgan topiklar ro'yxatida. Kutilmaydi."""
        if self.db.one("SELECT 1 FROM ignored_msgs WHERE chat_id=? AND msg_id=?", (chat_id, msg_id)):
            return True
        from .push import sending_now
        return sending_now(chat_id, topic)

    async def _is_bot(self, m) -> bool:
        sid = m.sender_id
        if sid is None:
            return False                                   # guruh/kanal nomidan — xodim
        if sid in self._bots:
            return True
        sender = getattr(m, "sender", None)
        if sender is None:
            try:
                sender = await asyncio.wait_for(m.get_sender(), timeout=3)
            except Exception:
                sender = None
        if sender is None:
            return False
        if getattr(sender, "bot", False):
            self._bots.add(int(sid))
            self.db.run("INSERT OR IGNORE INTO known_bots(user_id) VALUES(?)", (int(sid),))
            return True
        if hasattr(sender, "first_name"):
            self.note_human(int(sid), sender)
        return False

    def note_human(self, sid: int, sender) -> None:
        """Odam yozdi: ismi eslab qolinadi va @username xodimniki bo'lsa — Telegram ID si xodimga bog'lanadi
        (keyin shu xodim topikda ham, «Проёб»da ham, papka akkauntisiz ham tanildi). Har odam — bir marta."""
        uname = username_of(sender)
        name = f"@{uname}" if uname else " ".join(x for x in (getattr(sender, "first_name", "") or "",
                                                              getattr(sender, "last_name", "") or "") if x)
        key = (uname or "", name)
        if self._humans.get(sid) == key:
            return
        self._humans[sid] = key
        self.db.run("INSERT INTO known_humans(user_id, name) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET "
                    "name=excluded.name", (sid, name[:60]))
        if uname:
            P.identify(self.db, sid, uname)

    def _bot_ui(self, m, chat_id: int, topic: int) -> bool:
        """Vositachi botning menyusi/javobi (status paneli, «Установлен: …») — mijoz xabari emas."""
        if BOT_UI_RE.match((getattr(m, "message", "") or "")[:40]):
            return True
        last = self._cmd_ts.get((chat_id, topic))
        if last is None:
            return False
        gap = m.date.timestamp() - last
        if 0 <= gap <= CMD_ECHO:                          # buyruqdan darhol keyin (karta, menyu) — botning javobi
            return True
        rm = getattr(m, "reply_markup", None)
        return rm is not None and type(rm).__name__ == "ReplyInlineMarkup" and 0 <= gap <= CMD_WINDOW

    async def _process(self, m, chat_id: int, topic: int, source: str, late: bool = False) -> str:
        action = getattr(m, "action", None)
        if source != "live" and action is not None and "TopicEdit" in type(action).__name__ and topic > 1:
            await self.refresh_topic(chat_id, topic)       # status (🔥/⚡/💊) o'zgardi — jonli kelmagan bo'lsa ham
        who = await self.classify(m, chat_id, topic)
        cmd = ""
        if who == "client" and self._bot_ui(m, chat_id, topic):
            who = "service"
        elif who == "staff" and (getattr(m, "message", "") or "").startswith("/"):
            self._cmd_ts[(chat_id, topic)] = m.date.timestamp()            # /status, /rek … — faqat buyruq so'zi
            cmd = m.message.split()[0].split("@")[0].lower()[:33]
            who = "service"
        msg = Msg(chat_id, topic, int(m.id), int(m.date.timestamp()), m.sender_id, who,
                  video=bool(getattr(m, "video_note", None)), source=source, cmd=cmd)
        if late:
            return await self.tracker.handle_late(msg)
        return await self.tracker.handle(msg)

    async def _fetch_and_process(self, chat_id: int, topic: int, min_id: int, upto: int | None, limit: int,
                                 tail: bool = False) -> int:
        """Nit xabarlarini Telegram'dan olib, eski→yangi tartibda ishlash. tail=True — faqat oxirgi `limit` ta."""
        if self.client is None:
            return 0
        reply_to = topic if topic > 1 else None
        msgs = []
        try:
            if tail:
                async for m in self.client.iter_messages(chat_id, limit=limit, reply_to=reply_to,
                                                         max_id=(upto + 1) if upto else 0):
                    msgs.append(m)
                msgs.reverse()
            else:
                async for m in self.client.iter_messages(chat_id, limit=limit, reply_to=reply_to, min_id=min_id,
                                                         reverse=True):
                    if upto is not None and int(m.id) > upto:
                        break
                    msgs.append(m)
        except Exception as exc:
            log.info("Xabarlar olinmadi %s/%s: %s", chat_id, topic, type(exc).__name__)
            return 0
        n = 0
        for m in msgs:
            if reply_to is None and thread_of(m, False) != topic:
                continue
            await self._process(m, chat_id, topic, "catchup")
            n += 1
        return n

    # ------------------------------------------------------------ Push bazasi: to'liq tekshirish
    async def deep_scan(self, force: bool = False) -> int | None:
        """Push bazasi 100%: baza sanasidan keyin lidning O'ZI yozgan xabarlari (vositachi bot orqali). CRM'ning o'z
        xabarlari sanalmaydi: menyu va status («Статус: …», «Установлен: …», «Реквизиты отправлены»), xodim
        buyrug'iga (/rek, /status …) javob. Har chat bo'yicha baza QAYTADAN yoziladi (eski noto'g'ri sanalganlar
        chiqadi). Matn saqlanmaydi — faqat kim va qachon. Baza sanasi yoki qoida o'zgarmaguncha qayta ishlamaydi.
        -> topilgan lidlar soni yoki None (kerak emas / ketyapti)."""
        from datetime import datetime, time as dtime
        from .timeutil import parse_date
        if self.client is None or self.deep_running:
            return None
        base_iso = self.db.get("push_base_from") or "2026-08-28"
        if not force and self.db.get("deep_scan_base") == base_iso and self.db.get("deep_scan_v") == DEEP_SCAN_V:
            return None
        try:
            base_ts = int(datetime.combine(parse_date(base_iso), dtime(0, 0), tzinfo=self.tz).timestamp())
        except ValueError:
            return None
        self.deep_running = True
        started = int(time.time())
        leads: set = set()
        failed = 0
        try:
            for chat_id in list(self.tracker.chat_folder):
                try:
                    found = await self._scan_chat(chat_id, base_ts)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    failed += 1
                    log.warning("Bazani tekshirish: %s o'qilmadi (%s)", chat_id, type(exc).__name__)
                    continue
                self._rewrite_base(chat_id, found, base_ts, started)
                leads |= {(chat_id, t) for t in found}
            from .push import base_count
            n = base_count(self.db, base_ts)                            # bazadagi lidlar: shu sanadan keyin yozganlar
            self.db.set("deep_scan_n", str(n))
            self.db.set("deep_scan_ts", str(int(time.time())))
            if not failed:
                self.db.set("deep_scan_base", base_iso)                 # tugadi — keyingi sinxronda qaytarilmaydi
                self.db.set("deep_scan_v", DEEP_SCAN_V)
            from .context import tr
            d = f"{base_iso[8:10]}.{base_iso[5:7]}"
            await self.notifier.notify_owner(lambda: (tr(
                f"✅ Push bazasi to'liq tekshirildi: {d} dan keyin o'zi yozgan lidlar — {n} ta." +
                (f" ⚠️ {failed} ta guruh o'qilmadi, keyinroq qayta uriniladi." if failed else ""),
                f"✅ База Пуш проверена полностью: писали сами после {d} — {n}." +
                (f" ⚠️ {failed} групп(ы) не прочитаны, повторю позже." if failed else "")), None),
                key="deepscan")
            return n
        finally:
            self.deep_running = False

    async def _scan_chat(self, chat_id: int, base_ts: int) -> dict[int, tuple[int, int]]:
        """Chatdagi baza sanasidan keyingi hamma xabar (yangi → eski). -> {topik: (lid birinchi, oxirgi o'zi yozgani)}.
        Telegram «kuting» desa — kutib, to'xtagan joyidan davom etadi."""
        from telethon import errors
        forum = chat_id in self.tracker.forums
        entity = await self.client.get_input_entity(chat_id)
        events: dict[int, list] = {}                                    # topik -> [(ts, tur)]
        offset, finished = 0, False
        while not finished:
            try:
                finished = True
                async for m in self.client.iter_messages(entity, limit=None, offset_id=offset):
                    offset = int(m.id)
                    ts = _unix(m.date) or 0
                    if ts < base_ts:
                        break                                           # yangi → eski: bazadan oldingisi kerak emas
                    if getattr(m, "action", None) is not None:
                        continue
                    topic = thread_of(m, forum)
                    if forum and topic == 1:
                        continue
                    if m.out or m.sender_id in self._push_ids:
                        kind = "us"                                     # bizning akkaunt (Push yoki xodim)
                    elif await self._is_bot(m):
                        text = (getattr(m, "message", "") or "")[:40]
                        rm = getattr(m, "reply_markup", None)
                        kind = "ui" if BOT_UI_RE.match(text) else ("menu" if rm is not None and
                                                                   type(rm).__name__ == "ReplyInlineMarkup" else "bot")
                    else:
                        kind = "cmd" if (getattr(m, "message", "") or "").startswith("/") else "staff"
                    events.setdefault(topic, []).append((ts, kind))
            except errors.FloodWaitError as exc:
                finished = False
                log.info("Bazani tekshirish: Telegram %s s kutishni so'radi", exc.seconds)
                await asyncio.sleep(int(exc.seconds) + 1)
        out: dict[int, tuple[int, int]] = {}
        for topic, evs in events.items():
            evs.sort()
            last_cmd = None
            for ts, kind in evs:
                if kind == "cmd":
                    last_cmd = ts
                    continue
                if kind not in ("bot", "menu"):
                    continue
                if last_cmd is not None and 0 <= ts - last_cmd <= (CMD_WINDOW if kind == "menu" else CMD_ECHO):
                    continue                                            # buyruqqa CRM javobi/menyusi — lid yozmagan
                fs, ls = out.get(topic, (ts, ts))
                out[topic] = (min(fs, ts), max(ls, ts))
        return out

    def _rewrite_base(self, chat_id: int, found: dict, base_ts: int, started: int) -> None:
        """Shu chat bo'yicha baza qaytadan: lid o'zi yozgan oxirgi vaqt. Tekshiruv paytida jonli kelganlari saqlanadi."""
        for topic, (fs, ls) in found.items():
            self.db.run("INSERT INTO threads(chat_id, topic_id, first_seen, last_seen) VALUES(?,?,?,?) "
                        "ON CONFLICT(chat_id, topic_id) DO UPDATE SET "
                        "first_seen=CASE WHEN threads.first_seen IS NULL OR threads.first_seen>=? "
                        "THEN excluded.first_seen ELSE threads.first_seen END, "
                        "last_seen=CASE WHEN threads.last_seen>=? THEN threads.last_seen ELSE excluded.last_seen END",
                        (chat_id, topic, fs, ls, base_ts, started))
        keep = set(found)
        for th in self.db.all("SELECT topic_id FROM threads WHERE chat_id=? AND last_seen>=? AND last_seen<?",
                              (chat_id, base_ts, started)):
            if th["topic_id"] not in keep:                              # baza sanasidan keyin o'zi yozmagan
                self.db.run("UPDATE threads SET last_seen=NULL WHERE chat_id=? AND topic_id=?",
                            (chat_id, th["topic_id"]))

    # ------------------------------------------------------------ o'tkazib yuborilganlarni olish
    async def catch_up(self) -> None:
        """Har bir nit: Telegram'dagi oxirgi xabar biz ishlagandan yangi bo'lsa — yetishmaganlarini olib ishlaymiz."""
        if self.client is None:
            return
        wanted = set(self.tracker.chat_folder)
        forums: list = []
        async for d in self.client.iter_dialogs(limit=None):
            if d.id not in wanted:
                continue
            is_forum = bool(getattr(d.entity, "forum", False))
            self.db.run("UPDATE chats SET title=?, is_forum=? WHERE chat_id=?", (d.name or "", int(is_forum), d.id))
            if is_forum:
                forums.append((d.id, d.input_entity))
                continue
            top = int(d.message.id) if d.message is not None else 0
            await self._catch_thread(d.id, 0, top, None)
        self.tracker.reload()
        for chat_id, peer in forums:
            try:
                await self._catch_forum(chat_id, peer)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Topiklar olinmadi %s", chat_id)

    async def _catch_thread(self, chat_id: int, topic: int, top_msg: int, created: int | None) -> None:
        async with self._lock:
            th = self.tracker.thread(chat_id, topic)
            if th is None:
                self.tracker.start_thread(chat_id, topic, created)
                th = self.tracker.thread(chat_id, topic)
                if th["stavka"] == "on":
                    await self._fetch_and_process(chat_id, topic, min_id=topic, upto=None, limit=TOPIC_FETCH_LIMIT)
                elif top_msg:
                    await self._fetch_and_process(chat_id, topic, 0, top_msg, OLD_THREAD_TAIL, tail=True)
                return
            if top_msg and top_msg > th["seen_msg_id"]:
                if th["seen_msg_id"] == 0 and th["stavka"] != "on":       # hali ishlanmagan eski nit — faqat oxiri
                    await self._fetch_and_process(chat_id, topic, 0, top_msg, OLD_THREAD_TAIL, tail=True)
                else:
                    await self._fetch_and_process(chat_id, topic, min_id=th["seen_msg_id"], upto=None,
                                                  limit=TOPIC_FETCH_LIMIT)

    async def _catch_forum(self, chat_id: int, peer) -> None:
        from telethon.tl.functions.channels import GetForumTopicsRequest
        offset_date, offset_id, offset_topic = None, 0, 0
        while True:
            res = await self.client(GetForumTopicsRequest(channel=peer, offset_date=offset_date, offset_id=offset_id,
                                                          offset_topic=offset_topic, limit=100))
            if not res.topics:
                break
            topics = [t for t in res.topics if hasattr(t, "title") and int(t.id) != 1]
            await self._store_topics(chat_id, topics)
            for t in topics:
                await self._catch_thread(chat_id, int(t.id), int(getattr(t, "top_message", 0) or 0),
                                         _unix(getattr(t, "date", None)))
            msgs = {int(m.id): m for m in res.messages}
            last = res.topics[-1]
            last_msg = msgs.get(int(getattr(last, "top_message", 0) or 0))
            if len(res.topics) < 100 or last_msg is None:
                break
            offset_date, offset_id, offset_topic = last_msg.date, int(last.top_message), int(last.id)
            await asyncio.sleep(0.3)

    async def _store_topics(self, chat_id: int, topics: list) -> None:
        icons = await self._icon_chars({int(t.icon_emoji_id) for t in topics if getattr(t, "icon_emoji_id", None)})
        changed, learned = [], []
        for t in topics:
            icon = icons.get(int(t.icon_emoji_id), "") if getattr(t, "icon_emoji_id", None) else ""
            old = self.db.one("SELECT icon, created_ts FROM topics WHERE chat_id=? AND topic_id=?", (chat_id, int(t.id)))
            if old is not None and old["icon"] != icon:
                changed.append(int(t.id))
            if (old is None or old["created_ts"] is None) and getattr(t, "date", None) is not None:
                learned.append(int(t.id))
            self.db.run("INSERT INTO topics(chat_id, topic_id, title, icon, created_ts) VALUES(?,?,?,?,?) "
                        "ON CONFLICT(chat_id, topic_id) DO UPDATE SET title=excluded.title, icon=excluded.icon, "
                        "created_ts=COALESCE(topics.created_ts, excluded.created_ts)",
                        (chat_id, int(t.id), t.title or "", icon, _unix(getattr(t, "date", None))))
        for tid in learned:                                # topik qachon ochilgani endi ma'lum (yangi lidmi?)
            self.tracker.topic_known(chat_id, tid)
        for tid in changed:                                # status ⚡/💊 bo'ldi — kutish va zaderjka bekor
            await self.tracker.status_changed(chat_id, tid)

    async def _icon_chars(self, doc_ids: set[int]) -> dict[int, str]:
        from telethon.tl.functions.messages import GetCustomEmojiDocumentsRequest
        known = {r["doc_id"]: r["ch"] for r in self.db.all("SELECT * FROM emoji_cache")} if doc_ids else {}
        missing = [i for i in doc_ids if i not in known]
        for i in range(0, len(missing), 100):
            try:
                docs = await self.client(GetCustomEmojiDocumentsRequest(document_id=missing[i:i + 100]))
            except Exception:
                break
            for doc in docs:
                for attr in getattr(doc, "attributes", []):
                    if type(attr).__name__ == "DocumentAttributeCustomEmoji":
                        ch = (getattr(attr, "alt", "") or "").replace("️", "")
                        if ch:
                            self.db.run("INSERT OR REPLACE INTO emoji_cache(doc_id, ch) VALUES(?,?)", (int(doc.id), ch))
                            known[int(doc.id)] = ch
        return known

    async def refresh_topic(self, chat_id: int, topic: int) -> None:
        """Topik nomi/ikonkasi o'zgargan bo'lishi mumkin (status 🔥/⚡/💊)."""
        await self._topic_created(chat_id, topic)

    # ------------------------------------------------------------ papkalar va xodimlar
    async def folder_titles(self) -> list[str]:
        """Asosiy akkauntdagi Telegram papkalari nomlari (📁 Papkalar ro'yxati uchun). Ulanmagan bo'lsa — oxirgisi."""
        if self.client is None or self.state != "online":
            return list(self.tg_folders)
        from telethon.tl.functions.messages import GetDialogFiltersRequest
        res = await self.client(GetDialogFiltersRequest())
        titles = []
        for f in getattr(res, "filters", res):
            t = getattr(f, "title", None)
            t = getattr(t, "text", t)
            if isinstance(t, str) and t.strip():
                titles.append(t.strip())
        self.tg_folders = titles
        return titles

    async def sync_folders(self) -> tuple[int, int]:
        from telethon import utils
        from telethon.tl.functions.messages import GetDialogFiltersRequest
        if self.client is None:
            return 0, 0
        res = await self.client(GetDialogFiltersRequest())
        filters = getattr(res, "filters", res)
        by_title: dict[str, set[int]] = {}
        titles: list[str] = []
        for f in filters:
            title = getattr(f, "title", None)
            title = getattr(title, "text", title)
            if not isinstance(title, str):
                continue
            ids: set[int] = set()
            for p in list(getattr(f, "include_peers", None) or []) + list(getattr(f, "pinned_peers", None) or []):
                try:
                    ids.add(int(utils.get_peer_id(p)))
                except Exception:
                    continue
            by_title.setdefault(folder_key(title), set()).update(ids)
            titles.append(title.strip())
        added = removed = 0
        missing = []
        for f in P.folders(self.db):
            ids = by_title.get(folder_key(f["name"]))
            if ids is None:
                missing.append(f["name"])
                continue
            a, r = P.sync_folder_chats(self.db, f["id"], ids)
            added += a
            removed += r
        self.missing_folders = missing
        self.tg_folders = titles
        self.tracker.reload()
        return added, removed

    async def resolve_people(self) -> int:
        """@username → Telegram ID (xodimni tanish uchun). Avval «Проёб» va RD guruhlari a'zolaridan (Telegram
        cheklamaydi), qolganlari — @username bo'yicha so'rov bilan (Telegram «kuting» desa — keyingi sinxronda)."""
        if self.client is None:
            return 0
        want = {p["username"]: p for p in self.db.all("SELECT * FROM people WHERE username<>'' AND tg_id IS NULL "
                                                       "AND active=1")}
        if not want:
            return 0
        done = 0
        chats = []
        gid = (self.db.get("proyob_group_id") or "").strip()
        if gid.lstrip("-").isdigit():
            chats.append(int(gid))
        chats += [c for c in self.tracker.chat_folder if c not in chats]
        for cid in chats[:40]:
            if not want:
                break
            try:
                async for u in self.client.iter_participants(cid, limit=500):
                    un = username_of(u).lower()
                    p = want.pop(un, None)
                    if p is not None and not getattr(u, "bot", False):
                        P.identify(self.db, int(u.id), un)
                        done += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.info("A'zolar olinmadi %s: %s", cid, type(exc).__name__)
            await asyncio.sleep(0.5)
        if time.time() < self._resolve_pause:
            return done
        for un, p in list(want.items()):
            try:
                ent = await self.client.get_entity(un)
                if not getattr(ent, "bot", False):
                    P.identify(self.db, int(ent.id), un)
                    done += 1
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                wait = getattr(exc, "seconds", None)
                if wait:                                   # Telegram cheklovi — qolganlari keyinroq
                    self._resolve_pause = time.time() + int(wait)
                    log.info("@username so'rovi: Telegram %s s kutishni so'radi", wait)
                    break
                log.info("@%s aniqlanmadi: %s", un, type(exc).__name__)
            await asyncio.sleep(2)
        return done

    async def search_dialogs(self, query: str, limit: int = 15) -> list[tuple[int, str, str]]:
        if self.client is None or self.state != "online":
            raise RuntimeError("asosiy akkaunt ulanmagan")
        q = query.strip().casefold()
        out = []
        async for d in self.client.iter_dialogs(limit=None):
            if q and q not in (d.name or "").casefold():
                continue
            kind = "channel" if (d.is_channel and not d.is_group) else "group" if d.is_group else "private"
            out.append((int(d.id), d.name or "", kind))
            if len(out) >= limit:
                break
        return out
