"""📣 «Проёб»da Push holati — hamma ko'radi: nima ketyapti (matn / ovozli …), har RD — nechtadan nechtasi ketdi.
Tugagach: shu xabar natija bilan yangilanadi, xodimlar belgilangan javob xabari keladi («Пуш завершён …»),
panel 5 daqiqadan keyin o'zi o'chadi. Pul yo'q. Telegram kuttirsa — «⏳ до 12:44»."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from . import people as P
from .gtext import esc, mentions, small

log = logging.getLogger("push_group")

KIND_RU = {"voice": "🎤 голосовое", "video_note": "⭕ кружок", "video": "🎬 видео", "photo": "🖼 фото",
           "audio": "🎵 аудио", "animation": "🎞 gif", "document": "📄 файл"}
EVERY = 15                   # soniya: Push ketayotganda panel shunchada bir yangilanadi (son o'zgargan bo'lsa)
DELETE_AFTER = 5 * 60        # Push tugagach panel shuncha vaqtdan keyin o'chadi
PREVIEW = 300                # Push matnidan ko'rsatiladigan qism (belgi)
TITLES = {"done": "✅ Пуш завершён", "stopped": "⏹ Пуш остановлен", "aborted": "⛔ Пуш прерван"}


class GroupPanel:
    def __init__(self, pusher, bid: int, text: str, media: dict | None):
        self.pu, self.db, self.n = pusher, pusher.db, pusher.notifier
        self.bid, self.body, self.media = bid, text or "", media
        self.gid: int | None = None
        self.mid: int | None = None
        self.shown = ""
        self.started = int(pusher.clock())

    def _hm(self, ts: int) -> str:
        return datetime.fromtimestamp(ts, self.pu.tz).strftime("%H:%M")

    def render(self, snap: dict, final: str | None = None) -> str:
        if final is None:
            lines = [f"<b>📣 Пуш идёт</b> · с {self._hm(self.started)}"]
        else:
            lines = [f"<b>{TITLES.get(final, '📣 Пуш')}</b> · {self._hm(self.started)}–{self._hm(int(self.pu.clock()))}"]
        if self.media:
            lines.append(KIND_RU.get(self.media.get("kind"), "📎 вложение") + (" + текст" if self.body else ""))
        if self.body:
            t = self.body if len(self.body) <= PREVIEW else self.body[:PREVIEW].rstrip() + "…"
            lines.append(f"<blockquote>{esc(t)}</blockquote>")
        for x in snap["rows"]:
            line = f"{esc(x['name'])} — <b>{x['sent']}</b> / {x['total']}"
            if x.get("wait") and final is None:
                line += f" · ⏳ ждём до {self._hm(x['wait'])}"
            lines.append(line)
        lines.append(f"Всего: <b>{snap['sent']}</b> / {snap['total']}")
        return "\n".join(lines)

    async def start(self, snap: dict) -> None:
        """Push boshlandi — panel (ovozsiz). Davom ettirilgan Push — o'sha panel xabari yangilanadi."""
        gid = self.n.group_id()
        saved = (self.db.get("push_panel") or "").split(":")
        if len(saved) == 3 and saved[0] == str(self.bid) and saved[1] == str(gid) and saved[2].isdigit():
            self.gid, self.mid = gid, int(saved[2])
            await self.update(snap, force=True)
            if self.mid:
                return
        text = self.render(snap)
        msg = await self.n._call(self.n.bot.send_message, chat_id=gid, text=text, parse_mode="HTML",
                                 disable_notification=True, disable_web_page_preview=True)
        self.gid, self.mid, self.shown = msg.chat.id, msg.message_id, text
        self.db.set("push_panel", f"{self.bid}:{self.gid}:{self.mid}")

    async def update(self, snap: dict, force: bool = False, final: str | None = None) -> None:
        if not self.mid:
            return
        text = self.render(snap, final)
        if text == self.shown and not force:
            return
        try:
            await self.n._call(self.n.bot.edit_message_text, chat_id=self.gid, message_id=self.mid, text=text,
                               parse_mode="HTML", disable_web_page_preview=True)
            self.shown = text
        except Exception as exc:
            low = str(exc).lower()
            if "not modified" in low:
                self.shown = text
            elif any(k in low for k in ("not found", "can't be edited", "message to edit")):
                self.mid = None                          # kimdir o'chirib yuborgan — endi yangilanmaydi
            else:
                log.info("Push paneli yangilanmadi: %s", exc)

    async def loop(self, snap_fn) -> None:
        while True:
            await asyncio.sleep(EVERY)
            try:
                await self.update(snap_fn())
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Push paneli")

    async def finish(self, snap: dict, status: str) -> None:
        """Natija panelda; RD xodimlariga javob xabari (belgilab); 5 daqiqadan keyin panel o'chadi."""
        await self.update(snap, force=True, final=status)
        if snap["sent"]:
            people, seen = [], set()
            for x in snap["rows"]:
                if not x["sent"]:
                    continue
                for p in P.folder_people(self.db, x["fid"]):
                    if p["id"] not in seen:
                        seen.add(p["id"])
                        people.append(p)
            lines = [f"<b>{TITLES.get(status, '📣 Пуш')}</b> — отправлено <b>{snap['sent']}</b>",
                     " · ".join(f"{esc(x['name'])} — {x['sent']}" for x in snap["rows"] if x["sent"])]
            if people:
                lines.append(small(mentions(people) + " — лиды скоро начнут отвечать, будьте на связи 💬"))
            try:
                await self.n.send_group("\n".join(lines), reply_to=self.mid, trash="info")
            except Exception as exc:
                log.info("Push natijasi guruhga yuborilmadi: %s", exc)
        if self.mid:
            self.db.set("push_panel_del", f"{self.gid}:{self.mid}:{int(self.pu.clock()) + DELETE_AFTER}")
        self.db.set("push_panel", "")


async def cleanup(ctx, now: int) -> None:
    """Push tugaganiga 5 daqiqa bo'ldi — panel o'chadi (natija xabari qoladi)."""
    raw = (ctx.db.get("push_panel_del") or "").split(":")
    if len(raw) != 3 or not raw[2].isdigit() or now < int(raw[2]):
        return
    ctx.db.set("push_panel_del", "")
    try:
        await ctx.notifier.bot.delete_message(chat_id=int(raw[0]), message_id=int(raw[1]))
    except Exception as exc:
        log.info("Push paneli o'chmadi: %s", exc)
