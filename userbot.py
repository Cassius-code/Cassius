"""Asosiy akkaunt (Telethon) — botning «ko'zi». Xabardan faqat metama'lumot olinadi: chat, topik, id, vaqt,
yuboruvchi (bot/odam), dumaloq videomi. Matn o'qilmaydi va saqlanmaydi.

Jonli xabarlar va qayta ulanishda o'tkazib yuborilganlar BITTA yo'ldan ishlanadi (Tracker.handle), nit ichida id
tartibida. Yangi topik birinchi marta ko'rilganda uning boshidan xabarlari olinadi — stavka to'g'ri sanaladi.
"""
from __future__ import annotations

import asyncio
import logging
import time

from . import people as P
from .rules import Msg, Tracker
from .tgclient import TgAccount

log = logging.getLogger("userbot")

TOPIC_FETCH_LIMIT = 300        # yangi topik: boshidan nechta xabar olinadi
OLD_THREAD_TAIL = 15           # eski (o'rnatishdan oldingi) nit birinchi ko'rilganda: oxirgi nechta xabar
SYNC_EVERY = 600               # papka/topik sinxroni va tekshiruv har necha soniyada


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


class Userbot(TgAccount):
    def __init__(self, cfg, db, tracker: Tracker, notifier, tz):
        super().__init__(cfg, db, notifier)
        self.tracker = tracker
        self.tz = tz
        self._lock = asyncio.Lock()
        self.last_sync = 0.0
        self.last_event = 0.0
        self.missing_folders: list[str] = []
        self._push_ids: set[int] = set()
        self._bots: set[int] = set()
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
        log.info("Asosiy akkaunt ulandi: %s", self.me_label)
        asyncio.create_task(self._initial_sync())

    async def _initial_sync(self) -> None:
        try:
            await self.sync_all()
        except Exception:
            log.exception("Boshlang'ich sinxron xatosi")

    async def periodic(self, client) -> None:
        if time.time() - self.last_sync >= SYNC_EVERY:
            await self.sync_all()

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

    # ------------------------------------------------------------ jonli xabar
    async def _on_event(self, event) -> None:
        try:
            chat_id = event.chat_id
            if chat_id is None or not self.tracker.is_monitored(chat_id):
                return
            m = event.message
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
    async def classify(self, m, chat_id: int) -> str:
        if getattr(m, "action", None) is not None:
            return "service"
        if self.db.one("SELECT 1 FROM ignored_msgs WHERE chat_id=? AND msg_id=?", (chat_id, int(m.id))):
            return "ours"
        sid = m.sender_id
        if sid is not None and sid in self._push_ids:
            # papka akkaunti: xodim undan mijozga JAVOB yozadi (jurnal: RD 7 da deyarli hamma javob shundan).
            # Faqat Push yuborgan xabar (ignored_msgs da) «biz»; qolgani — xodim javobi.
            return "ours" if await self._is_push_message(chat_id, int(m.id)) else "staff"
        if m.out:
            return "staff"                                 # asosiy akkauntdan yozilgan — javob
        is_bot = await self._is_bot(m)
        return "client" if is_bot else "staff"

    async def _is_push_message(self, chat_id: int, msg_id: int) -> bool:
        """Push yuborgan xabarmi? Push ketayotgan bo'lsa, yozuv paydo bo'lishini 4 soniyagacha kutamiz
        (xabar hodisasi yuboruvchi qayd etishidan oldin kelishi mumkin)."""
        q = "SELECT 1 FROM ignored_msgs WHERE chat_id=? AND msg_id=?"
        if self.db.one(q, (chat_id, msg_id)):
            return True
        if not self.db.one("SELECT 1 FROM broadcasts WHERE status='running'"):
            return False
        for _ in range(8):
            await asyncio.sleep(0.5)
            if self.db.one(q, (chat_id, msg_id)):
                return True
        return False

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
            uname = getattr(sender, "username", None)
            name = f"@{uname}" if uname else " ".join(x for x in (sender.first_name or "", getattr(sender, "last_name", "")
                                                                   or "") if x)
            self.db.run("INSERT INTO known_humans(user_id, name) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET "
                        "name=excluded.name", (int(sid), name[:60]))
        return False

    async def _process(self, m, chat_id: int, topic: int, source: str) -> str:
        who = await self.classify(m, chat_id)
        msg = Msg(chat_id, topic, int(m.id), int(m.date.timestamp()), m.sender_id, who,
                  video=bool(getattr(m, "video_note", None)), source=source)
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
        for t in topics:
            icon = icons.get(int(t.icon_emoji_id), "") if getattr(t, "icon_emoji_id", None) else ""
            self.db.run("INSERT INTO topics(chat_id, topic_id, title, icon, created_ts) VALUES(?,?,?,?,?) "
                        "ON CONFLICT(chat_id, topic_id) DO UPDATE SET title=excluded.title, icon=excluded.icon, "
                        "created_ts=COALESCE(topics.created_ts, excluded.created_ts)",
                        (chat_id, int(t.id), t.title or "", icon, _unix(getattr(t, "date", None))))

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
    async def sync_folders(self) -> tuple[int, int]:
        from telethon import utils
        from telethon.tl.functions.messages import GetDialogFiltersRequest
        if self.client is None:
            return 0, 0
        res = await self.client(GetDialogFiltersRequest())
        filters = getattr(res, "filters", res)
        by_title: dict[str, set[int]] = {}
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
            by_title.setdefault(title.strip().casefold(), set()).update(ids)
        added = removed = 0
        missing = []
        for f in P.folders(self.db):
            ids = by_title.get(f["name"].strip().casefold())
            if ids is None:
                missing.append(f["name"])
                continue
            a, r = P.sync_folder_chats(self.db, f["id"], ids)
            added += a
            removed += r
        self.missing_folders = missing
        self.tracker.reload()
        return added, removed

    async def resolve_people(self) -> int:
        """@username → Telegram ID (xodimni guruhda tanish uchun)."""
        if self.client is None:
            return 0
        done = 0
        for p in self.db.all("SELECT * FROM people WHERE username<>'' AND tg_id IS NULL AND active=1"):
            try:
                ent = await self.client.get_entity(p["username"])
                self.db.run("UPDATE people SET tg_id=? WHERE id=?", (int(ent.id), p["id"]))
                done += 1
            except Exception as exc:
                log.info("@%s aniqlanmadi: %s", p["username"], type(exc).__name__)
            await asyncio.sleep(1)
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
