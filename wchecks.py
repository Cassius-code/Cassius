"""🔗 Xodim chekni botga yozadi: topik havolasi + summa (egasi, 2026-11-04).

* Xodim botga (shaxsiy chatda) yozadi: «https://t.me/c/1234567890/56» va pastida summa («1950», «11) 1950»,
  «3.500»). Bot 👍 bosadi va hisoblab boradi. Havola qaysi RD ekanini va lid qachon kelganini (topik ochilgan kun)
  bildiradi — buni bot o'z bazasidan oladi (asosiy akkaunt kuzatadigan guruhlar).
* Xato bo'lsa — o'sha xabarga javob qilib /delete: hisobdan chiqadi, xabar chatda qoladi, bot 👎 bosadi.
* Xabar tahrirlansa (2000 → 1970) — bot qayta o'qiydi va javob yozadi: «✏️ Изменено: 2000 → 1970 ✅» yoki
  «✅ Принято»; bu javob 5 daqiqada o'chadi.
* Topik bizning RD larda topilmasa (xodim bizga aloqasi yo'q RD da ishlagan) — bot chek ostida so'raydi:
  «Когда пришёл лид?»; xodim sanani yozadi («10.09») — achotga o'sha kun qo'yiladi (egasi, 2026-11-04).
* Kechqurun /gaz — bot tayyor achotni beradi (bitta oddiy xabar, har chekda RD raqami; «RD 3.1» ham «Rd3»):
      10.09 1950
      Rd3 04.11
  Xodim uni «Проёб»ga tashlaydi — kassa o'sha yerda hozirgidek hisoblanadi. Havola qaysi RD dan bo'lishidan qat'i
  nazar kassa ham, zp ham achotni tashlagan xodimniki (egasi, 2026-11-04). Bu yerda kassaga hech narsa yozilmaydi.
Xabar matni saqlanmaydi: faqat summa, topik raqami, RD va vaqt."""
from __future__ import annotations

import datetime as dt
import logging
import re
import time

from . import kassa as K
from .timeutil import fmt, local_date

log = logging.getLogger("wchecks")

LINK_RE = re.compile(r"(?:https?://)?(?:t|telegram)\.me/c/(\d{5,})/(\d+)(?:/(\d+))?(?:\?thread=(\d+))?", re.I)
NUMBERING = re.compile(r"(?m)^\s*\d{1,3}[).]\s+")          # «11) 1950» — tartib raqami summa emas
CMD_GAZ = ("/gaz",)
CMD_DEL = ("/delete", "/del")


def _cmd(text: str) -> str:
    t = (text or "").strip().split()
    return t[0].split("@")[0].lower() if t and t[0].startswith("/") else ""


def _amounts(seg: str) -> list[int]:
    seg = NUMBERING.sub(" ", seg)
    out: list[int] = []
    for line in seg.splitlines():
        out += K.line_amounts(line)
    return out


def parse(text: str) -> list[dict]:
    """Xabardagi havolalar va ularning summalari: [{chat, topic, amounts}]. Havolasiz xabar — [] (chek emas)."""
    text = text or ""
    links = list(LINK_RE.finditer(text))
    out = []
    for i, m in enumerate(links):
        end = links[i + 1].start() if i + 1 < len(links) else len(text)
        amts = _amounts(text[m.end():end])
        if not amts and i == 0:                            # summa havoladan oldin yozilgan bo'lsa
            amts = _amounts(text[:m.start()])
        topic = int(m.group(4) or m.group(2))
        out.append({"chat": int(f"-100{m.group(1)}"), "topic": topic, "amounts": amts})
    return out


def topic_info(db, chat_id: int, topic_id: int):
    """-> (papka id | None, lid kelgan vaqt | None). Asosiy akkaunt kuzatadigan guruhlar bo'yicha."""
    c = db.one("SELECT folder_id, is_forum FROM chats WHERE chat_id=?", (chat_id,))
    if c is None:
        return None, None
    ts = None
    if c["is_forum"]:
        t = db.one("SELECT created_ts FROM topics WHERE chat_id=? AND topic_id=?", (chat_id, topic_id))
        ts = t["created_ts"] if t else None
        if ts is None:
            th = db.one("SELECT first_seen FROM threads WHERE chat_id=? AND topic_id=?", (chat_id, topic_id))
            ts = th["first_seen"] if th else None
    else:
        th = db.one("SELECT first_seen FROM threads WHERE chat_id=? AND topic_id=0", (chat_id,))
        ts = th["first_seen"] if th else None
    return c["folder_id"], ts


def rd_label(db, fid) -> str:
    """Papka nomidan achot yorlig'i: «RD 3» va «RD 3.1 🔥» → «Rd3» (egasi: «3.1» shart emas), raqamsiz yoki
    noma'lum — «Rd»."""
    f = db.one("SELECT name FROM folders WHERE id=?", (fid,)) if fid else None
    m = re.search(r"\d{1,2}", f["name"]) if f else None
    return f"Rd{m.group(0)}" if m else "Rd"


ASK = "📅 Не нашёл этот топик в наших RD. Когда пришёл лид? Ответьте на это сообщение датой, например: 10.09"
DATE_ONLY = re.compile(r"\s*\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\s*")


async def ask_lead(ctx, chat_id: int, msg_id: int, pid: int) -> None:
    """Topik topilmadi (bizga aloqasi yo'q RD) — lid qachon kelganini xodimdan so'raymiz (egasi, 2026-11-04)."""
    try:
        m = await ctx.bot.send_message(chat_id=chat_id, text=ASK, reply_to_message_id=msg_id)
    except Exception as exc:
        log.info("Savol yuborilmadi: %s", exc)
        return
    ctx.db.run("UPDATE wchecks SET ask_mid=? WHERE chat_id=? AND msg_id=? AND person_id=? AND topic_ts IS NULL "
               "AND lead_ts IS NULL", (m.message_id, chat_id, msg_id, pid))


async def _drop_ask(ctx, chat_id: int, rows) -> None:
    for mid in {x["ask_mid"] for x in rows if x["ask_mid"]}:
        try:
            await ctx.bot.delete_message(chat_id=chat_id, message_id=mid)
        except Exception:
            pass


async def on_lead_date(ctx, message, p) -> bool:
    """Xodim lid kelgan kunni yozdi («10.09»): savolga yoki chekka javob qilib — o'sha chekka, oddiy yozsa — oxirgi
    so'ralgan chekka. -> ishlandimi."""
    db = ctx.db
    text = message.text or ""
    if not DATE_ONLY.fullmatch(text):
        return False
    today = local_date(int(message.date.timestamp()), ctx.tz)
    days = K.parse_dates(text, today)
    if not days:
        return False
    chat_id = message.chat.id
    rt = getattr(message, "reply_to_message", None)
    base = "SELECT * FROM wchecks WHERE chat_id=? AND person_id=? AND deleted=0 AND topic_ts IS NULL"
    if rt is not None:
        rows = db.all(base + " AND (ask_mid=? OR msg_id=?)", (chat_id, p["id"], rt.message_id, rt.message_id))
    else:
        last = db.one(base + " AND ask_mid IS NOT NULL AND lead_ts IS NULL ORDER BY ts DESC, msg_id DESC LIMIT 1",
                      (chat_id, p["id"]))
        rows = db.all(base + " AND msg_id=?", (chat_id, p["id"], last["msg_id"])) if last else []
    if not rows:
        return False
    lead = int(dt.datetime.combine(days[0], dt.time(12), tzinfo=ctx.tz).timestamp())
    db.run("UPDATE wchecks SET lead_ts=?, ask_mid=NULL WHERE chat_id=? AND msg_id=? AND person_id=?",
           (lead, chat_id, rows[0]["msg_id"], p["id"]))
    await _drop_ask(ctx, chat_id, rows)
    await react(ctx, chat_id, message.message_id, "👍")
    await note(ctx, chat_id, f"✅ Дата лида: {days[0]:%d.%m}", reply_to=rows[0]["msg_id"])
    return True


def _store(ctx, p, chat_id: int, msg_id: int, sent_ts: int, items: list[dict]) -> tuple[int, int]:
    """Cheklarni yozish. -> (nechta chek, nechtasining topigi topilmadi)."""
    db = ctx.db
    day = local_date(sent_ts, ctx.tz).isoformat()
    n = unknown = pos = 0
    for it in items:
        fid, tts = topic_info(db, it["chat"], it["topic"])
        if fid is None or tts is None:
            unknown += len(it["amounts"])
        for a in it["amounts"]:
            db.run("INSERT INTO wchecks(person_id, chat_id, msg_id, pos, link_chat, link_topic, folder_id, topic_ts, "
                   "amount, day, ts) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (p["id"], chat_id, msg_id, pos, it["chat"], it["topic"], fid, tts, a, day, sent_ts))
            pos += 1
            n += 1
    return n, unknown


async def react(ctx, chat_id: int, msg_id: int, emoji: str) -> None:
    try:
        from aiogram.types import ReactionTypeEmoji
        await ctx.bot.set_message_reaction(chat_id=chat_id, message_id=msg_id, reaction=[ReactionTypeEmoji(emoji=emoji)])
    except Exception as exc:
        log.info("Reaksiya qo'yilmadi: %s", exc)


async def note(ctx, chat_id: int, text: str, reply_to: int | None = None) -> None:
    """Qisqa javob — 5 daqiqada o'zi o'chadi (🧹)."""
    from .tidy import remember
    try:
        kw = {"reply_to_message_id": reply_to} if reply_to else {}
        m = await ctx.bot.send_message(chat_id=chat_id, text=text, **kw)
        remember(ctx.db, chat_id, m.message_id, "p5", int(time.time()))
    except Exception as exc:
        log.info("Javob yozilmadi: %s", exc)


async def _drop_cmd(message) -> None:
    try:
        await message.delete()                             # buyruq xabari chatda qolmasin
    except Exception:
        pass


async def on_message(ctx, message, p) -> bool:
    """Xodimning shaxsiy chatdagi xabari: chek / /delete / /gaz. -> ishlandimi (yo'q bo'lsa — eski menyu)."""
    text = message.text or message.caption or ""
    cmd = _cmd(text)
    chat_id = message.chat.id
    if cmd in CMD_GAZ:
        await _drop_cmd(message)
        await send_report(ctx, chat_id, p)
        return True
    if cmd in CMD_DEL:
        await _drop_cmd(message)
        rt = getattr(message, "reply_to_message", None)
        if rt is None:
            await note(ctx, chat_id, "↩️ Ответьте /delete на сообщение с чеком.")
            return True
        rows = ctx.db.all("SELECT id, ask_mid FROM wchecks WHERE chat_id=? AND msg_id=? AND person_id=? AND deleted=0",
                          (chat_id, rt.message_id, p["id"]))
        if not rows:
            await note(ctx, chat_id, "⚠️ Это сообщение не чек (или уже удалён).", reply_to=rt.message_id)
            return True
        ctx.db.run("UPDATE wchecks SET deleted=1, ask_mid=NULL WHERE chat_id=? AND msg_id=? AND person_id=?",
                   (chat_id, rt.message_id, p["id"]))
        await _drop_ask(ctx, chat_id, rows)                # «Когда пришёл лид?» savoli ham ketadi
        await react(ctx, chat_id, rt.message_id, "👎")
        return True
    if await on_lead_date(ctx, message, p):                # «10.09» — lid kelgan kun (bot so'ragan edi)
        return True
    items = parse(text)
    if not items:
        return False
    sent_ts = int(message.date.timestamp())
    n, unknown = _store(ctx, p, chat_id, message.message_id, sent_ts, items)
    if not n:
        await react(ctx, chat_id, message.message_id, "👎")
        await note(ctx, chat_id, "⚠️ Сумма не найдена — чек не принят. Исправьте сообщение.",
                   reply_to=message.message_id)
        return True
    await react(ctx, chat_id, message.message_id, "👍")
    if unknown:                                            # bizga aloqasi yo'q RD — lid qachon kelganini so'raymiz
        await ask_lead(ctx, chat_id, message.message_id, p["id"])
    return True


async def on_edit(ctx, message, p) -> None:
    """Xabar tahrirlandi: qayta o'qiladi; «✏️ Изменено: 2000 → 1970 ✅» / «✅ Принято» (5 daqiqada o'chadi)."""
    db = ctx.db
    chat_id, mid = message.chat.id, message.message_id
    old = db.all("SELECT * FROM wchecks WHERE chat_id=? AND msg_id=? AND person_id=? ORDER BY pos",
                 (chat_id, mid, p["id"]))
    items = parse(message.text or message.caption or "")
    if not old and not items:
        return
    before = [x["amount"] for x in old if not x["deleted"]]
    reported = next((x["reported_ts"] for x in old if x["reported_ts"]), None)
    lead = next((x["lead_ts"] for x in old if x["lead_ts"]), None)        # xodim yozgan lid kuni qoladi
    ask = next((x["ask_mid"] for x in old if x["ask_mid"]), None)
    db.run("DELETE FROM wchecks WHERE chat_id=? AND msg_id=? AND person_id=?", (chat_id, mid, p["id"]))
    n, unknown = _store(ctx, p, chat_id, mid, int(message.date.timestamp()), items) if items else (0, 0)
    if reported:
        db.run("UPDATE wchecks SET reported_ts=? WHERE chat_id=? AND msg_id=?", (reported, chat_id, mid))
    if unknown and (lead or ask):
        db.run("UPDATE wchecks SET lead_ts=?, ask_mid=? WHERE chat_id=? AND msg_id=? AND topic_ts IS NULL",
               (lead, None if lead else ask, chat_id, mid))
    elif ask:                                              # endi topik topildi (yoki chek yo'q) — savol kerak emas
        await _drop_ask(ctx, chat_id, [{"ask_mid": ask}])
    after = [x["amount"] for x in db.all("SELECT amount FROM wchecks WHERE chat_id=? AND msg_id=? ORDER BY pos",
                                         (chat_id, mid))]
    if not n:
        await react(ctx, chat_id, mid, "👎")
        await note(ctx, chat_id, "❌ Не принято — сумма не найдена.", reply_to=mid)
        return
    await react(ctx, chat_id, mid, "👍")
    if before and before != after:
        txt = f"✏️ Изменено: {' '.join(map(str, before))} → {' '.join(map(str, after))} ✅"
    else:
        txt = "✅ Принято"
    await note(ctx, chat_id, txt, reply_to=mid)
    if unknown and not (lead or ask):
        await ask_lead(ctx, chat_id, mid, p["id"])


def report_rows(db, pid: int, today: str):
    """/gaz: bugungi cheklar va hali achotga kirmagan eskilari (o'chirilganlarsiz)."""
    return db.all("SELECT * FROM wchecks WHERE person_id=? AND deleted=0 AND (day=? OR (reported_ts IS NULL AND day<?)) "
                  "ORDER BY ts, msg_id, pos", (pid, today, today))


def report_text(ctx, rows) -> str:
    """Bitta achot: har chek — «10.09 1950» (lid kelgan kun va summa) va «Rd3 04.11» (RD va yozilgan kun)."""
    lines = []
    for i, x in enumerate(rows):
        if i:
            lines.append("")
        ts = x["topic_ts"] or x["lead_ts"]                 # topik ochilgan kun yoki xodim yozgani
        lead = fmt(ts, ctx.tz, "%d.%m") + " " if ts else ""
        lines.append(f"{lead}{x['amount']}")
        lines.append(f"{rd_label(ctx.db, x['folder_id'])} {x['day'][8:10]}.{x['day'][5:7]}")
    return "\n".join(lines)


async def send_report(ctx, chat_id: int, p) -> None:
    db = ctx.db
    today = local_date(ctx.clock(), ctx.tz).isoformat()
    rows = report_rows(db, p["id"], today)
    if not rows:
        await note(ctx, chat_id, "Сегодня чеков нет.")
        return
    try:
        await ctx.bot.send_message(chat_id=chat_id, text=report_text(ctx, rows))
    except Exception as exc:
        log.info("Achot yuborilmadi: %s", exc)
    miss = sum(1 for x in rows if not (x["topic_ts"] or x["lead_ts"]))
    if miss:
        await note(ctx, chat_id, f"⚠️ Без даты лида: {miss} — ответьте датой на вопрос «Когда пришёл лид?» и снова /gaz.")
    now = int(ctx.clock())
    for x in rows:
        if not x["reported_ts"]:
            db.run("UPDATE wchecks SET reported_ts=? WHERE id=?", (now, x["id"]))
