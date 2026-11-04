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
NUMBERING = re.compile(r"(?m)^\s*\d{1,2}[).]\s+")          # «11) 1950» — tartib raqami summa emas
CMD_GAZ = ("/gaz",)
GAZ_ASK_SEC = 3 * 3600      # /gaz dan keyin shuncha vaqt ichida yangi chek — «за какой день?» (egasi: 2–3 soat)
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


PLAIN_OK = re.compile(r"[\d\s.,;:/()+=\-–—]+")             # havolasiz chek: faqat raqam, sana, belgilar


def _plain(text: str, ref) -> list[dict]:
    """Havolasiz chek — asosiy akkaunt ko'rmaydigan RD (egasi, 2026-11-04): «1950 10.09», «1950\n10.09»,
    «1950. 10.09» (summa va lid kelgan kun), «10.09\n1950» ham. Sanasiz «1950» — bot sanani so'raydi."""
    if not PLAIN_OK.fullmatch(text) or K.is_phone(text):
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    out, pend, i = [], None, 0
    while i < len(lines):
        ln = NUMBERING.sub(" ", lines[i])
        amts, ds = K.line_amounts(ln), K.parse_dates(ln, ref)
        if not amts:
            pend = ds[0] if ds and DATE_ONLY.fullmatch(lines[i]) else None
            i += 1
            continue
        if not ds and i + 1 < len(lines) and DATE_ONLY.fullmatch(lines[i + 1]):
            ds = K.parse_dates(lines[i + 1], ref)
            i += 1
        if not ds and pend:
            ds = [pend]
        pend = None
        if len(ds) == len(amts) > 1:
            out += [{"chat": None, "topic": None, "amounts": [a], "lead": d} for a, d in zip(amts, ds)]
        else:
            out.append({"chat": None, "topic": None, "amounts": amts, "lead": ds[0] if ds else None})
        i += 1
    return out


def parse(text: str, ref=None) -> list[dict]:
    """Xabardagi cheklar: [{chat, topic, amounts, lead}]. Havola bo'lsa — havola va undan keyingi summa; havolasiz —
    summa va lid kelgan kun («1950 10.09»). Chekka o'xshamasa — [] (oddiy matn)."""
    text = text or ""
    links = list(LINK_RE.finditer(text))
    if not links:
        return [] if K.RD_FIND.search(text) else _plain(text, ref)      # «Rd 04.11» — achot, chek emas
    out = []
    for i, m in enumerate(links):
        end = links[i + 1].start() if i + 1 < len(links) else len(text)
        amts = _amounts(text[m.end():end])
        if not amts and i == 0:                            # summa havoladan oldin yozilgan bo'lsa
            amts = _amounts(text[:m.start()])
        topic = int(m.group(4) or m.group(2))
        out.append({"chat": int(f"-100{m.group(1)}"), "topic": topic, "amounts": amts, "lead": None})
    return out


def link_state(db, chat_id: int, topic_id: int) -> str:
    """Havola: ok — bizning RD dagi lid topigi (yoki oddiy guruh); general — guruhimizda, lekin lid topigi emas
    («General» yoki topiksiz xabar); unknown — bot bilmaydigan guruh."""
    c = db.one("SELECT is_forum FROM chats WHERE chat_id=?", (chat_id,))
    if c is None:
        return "unknown"
    if not c["is_forum"]:
        return "ok"
    if topic_id <= 1:
        return "general"
    known = db.one("SELECT 1 FROM topics WHERE chat_id=? AND topic_id=?", (chat_id, topic_id)) or \
        db.one("SELECT 1 FROM threads WHERE chat_id=? AND topic_id=?", (chat_id, topic_id))
    return "ok" if known else "general"


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
ASK_PLAIN = "📅 Когда пришёл лид? Ответьте на это сообщение датой, например: 10.09"      # havolasiz, sanasiz chek
DATE_ONLY = re.compile(r"\s*\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?\s*")


async def ask_lead(ctx, chat_id: int, msg_id: int, pid: int, text: str = ASK) -> None:
    """Topik topilmadi (bizga aloqasi yo'q RD) — lid qachon kelganini xodimdan so'raymiz (egasi, 2026-11-04)."""
    try:
        m = await ctx.bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=msg_id)
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


def _store(ctx, p, chat_id: int, msg_id: int, sent_ts: int, items: list[dict]) -> tuple[int, int, int]:
    """Cheklarni yozish. -> (nechta chek, nechtasining lid kuni noma'lum, nechta «General» havolasi — yozilmadi)."""
    db = ctx.db
    day = local_date(sent_ts, ctx.tz).isoformat()
    n = unknown = general = pos = 0
    for it in items:
        lead = None
        if it["chat"] is None:                             # havolasiz: lid kuni xodim yozgan
            fid, tts = None, None
            if it["lead"]:
                lead = int(dt.datetime.combine(it["lead"], dt.time(12), tzinfo=ctx.tz).timestamp())
        else:
            if link_state(db, it["chat"], it["topic"]) == "general":
                general += 1                               # lid topigi emas — 🧐, hisobga kirmaydi
                continue
            fid, tts = topic_info(db, it["chat"], it["topic"])
        if tts is None and lead is None:
            unknown += len(it["amounts"])
        for a in it["amounts"]:
            db.run("INSERT INTO wchecks(person_id, chat_id, msg_id, pos, link_chat, link_topic, folder_id, topic_ts, "
                   "lead_ts, amount, day, ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (p["id"], chat_id, msg_id, pos, it["chat"], it["topic"], fid, tts, lead, a, day, sent_ts))
            pos += 1
            n += 1
    return n, unknown, general


async def react(ctx, chat_id: int, msg_id: int, emoji: str, fallback: str = "") -> None:
    """Reaksiya. Telegram botga hamma emojini bermaydi — bo'lmasa fallback (🧐 → 🤨)."""
    from aiogram.types import ReactionTypeEmoji
    for e in (emoji, fallback):
        if not e:
            continue
        try:
            await ctx.bot.set_message_reaction(chat_id=chat_id, message_id=msg_id, reaction=[ReactionTypeEmoji(emoji=e)])
            return
        except Exception as exc:
            log.info("Reaksiya %s qo'yilmadi: %s", e, exc)


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
        rows = ctx.db.all("SELECT id, ask_mid, amount, day, reported_ts FROM wchecks WHERE chat_id=? AND msg_id=? "
                          "AND person_id=? AND deleted=0", (chat_id, rt.message_id, p["id"]))
        if not rows:
            await note(ctx, chat_id, "⚠️ Это сообщение не чек (или уже удалён).", reply_to=rt.message_id)
            return True
        ctx.db.run("UPDATE wchecks SET deleted=1, ask_mid=NULL WHERE chat_id=? AND msg_id=? AND person_id=?",
                   (chat_id, rt.message_id, p["id"]))
        await _drop_ask(ctx, chat_id, rows)                # «Когда пришёл лид?» savoli ham ketadi
        await react(ctx, chat_id, rt.message_id, "👎")
        if any(x["reported_ts"] for x in rows):            # achotga kirgan edi — kassada ham to'g'rilanadi
            await kassa_sync(ctx, p, chat_id, rt.message_id, rows[0]["day"], [x["amount"] for x in rows], [])
        return True
    if await on_lead_date(ctx, message, p):                # «10.09» — lid kelgan kun (bot so'ragan edi)
        return True
    sent_ts = int(message.date.timestamp())
    items = parse(text, local_date(sent_ts, ctx.tz))
    if not items:
        return False
    n, unknown, general = _store(ctx, p, chat_id, message.message_id, sent_ts, items)
    if general:                                            # «General» havolasi — lid topigi emas (egasi: 🧐)
        await react(ctx, chat_id, message.message_id, "🧐", "🤨")
        if not n:
            return True
    elif not n:
        await react(ctx, chat_id, message.message_id, "👎")
        await note(ctx, chat_id, "⚠️ Сумма не найдена — чек не принят. Исправьте сообщение.",
                   reply_to=message.message_id)
        return True
    else:
        await react(ctx, chat_id, message.message_id, "👍")
    if unknown:                                            # bizga aloqasi yo'q RD — lid qachon kelganini so'raymiz
        await ask_lead(ctx, chat_id, message.message_id, p["id"],
                       ASK if any(it["chat"] for it in items) else ASK_PLAIN)
    if n:
        await ask_day(ctx, chat_id, message.message_id, p, sent_ts)
    return True


async def ask_day(ctx, chat_id: int, msg_id: int, p, sent_ts: int) -> None:
    """/gaz dan keyin 3 soat ichida yangi chek — qaysi kunga (egasi, 2026-11-04: achotdan keyin 2–3 soat yana
    nimadir bo'lib qolishi mumkin): achot kuni yoki keyingi kun. Tanlanmasa — xabar yozilgan kun."""
    raw = ctx.db.get(f"gaz:{p['id']}") or ""
    ts_s, _, day_s = raw.partition(":")
    if not ts_s.isdigit() or not day_s or not 0 <= sent_ts - int(ts_s) <= GAZ_ASK_SEC:
        return
    d0 = dt.date.fromisoformat(day_s)
    d1 = d0 + dt.timedelta(days=1)
    from .ui import kb
    markup = kb([(f"📅 {d0:%d.%m}", f"wd:{msg_id}:{d0:%Y%m%d}"), (f"📅 {d1:%d.%m}", f"wd:{msg_id}:{d1:%Y%m%d}")])
    try:
        await ctx.bot.send_message(chat_id=chat_id, text=f"📅 Отчёт за {d0:%d.%m} уже был. Этот чек за какой день?",
                                   reply_to_message_id=msg_id, reply_markup=markup)
    except Exception as exc:
        log.info("Kun savoli yuborilmadi: %s", exc)


async def on_day_cb(ctx, cb, data: str, p) -> None:
    """«wd:<chek xabari>:<kun>» — /gaz dan keyingi chek kuni tanlandi."""
    try:
        _w, mid_s, ymd = data.split(":")
        day = dt.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8])).isoformat()
        mid = int(mid_s)
    except (ValueError, IndexError):
        return
    chat_id = cb.message.chat.id
    n = ctx.db.run("UPDATE wchecks SET day=? WHERE chat_id=? AND msg_id=? AND person_id=? AND deleted=0",
                   (day, chat_id, mid, p["id"])).rowcount
    try:
        await ctx.bot.delete_message(chat_id=chat_id, message_id=cb.message.message_id)
    except Exception:
        pass
    if n:
        await note(ctx, chat_id, f"✅ Чек за {day[8:10]}.{day[5:7]}. Отправьте /gaz ещё раз — он войдёт в отчёт.",
                   reply_to=mid)


async def kassa_sync(ctx, p, chat_id: int, mid: int, day: str, before: list[int], after: list[int]) -> None:
    """Achotga kirgan chek o'zgardi yoki o'chdi (egasi, 2026-11-04: kechagi chekni tahrirlasa/o'chirsa ham xatosiz):
    * achot «Проёб»da qabul qilingan (kassada o'sha kun cheklari bor) — kassadagi chek ham o'zgaradi/o'chadi;
    * kun yopilgan — kassaga tegilmaydi, egaga xabar;
    * achot hali kassada yo'q — o'sha kunning cheklari keyingi /gaz achotiga qayta kiradi."""
    db = ctx.db
    rem, add = list(before), list(after)
    for a in list(rem):
        if a in add:
            rem.remove(a)
            add.remove(a)
    if not rem and not add:
        return
    rows = db.all("SELECT ch.id, ch.amount FROM checks ch JOIN reports r ON r.id=ch.report_id WHERE r.status='done' "
                  "AND ch.rd=? AND ch.skip=0 AND (r.person_id=? OR ch.pay=?) ORDER BY ch.id", (day, p["id"], p["id"]))
    dm = f"{day[8:10]}.{day[5:7]}"
    what = f"{' '.join(map(str, before)) or '—'} → {' '.join(map(str, after)) or '—'}"
    if not rows:                                           # achot hali tashlanmagan — kun keyingi /gaz ga to'liq
        db.run("UPDATE wchecks SET reported_ts=NULL WHERE person_id=? AND day=?", (p["id"], day))
        await note(ctx, chat_id, f"↻ Чек за {dm} изменён. Отправьте /gaz — в отчёт войдёт весь день {dm}.", reply_to=mid)
        return
    if K.is_closed(db, day):
        from .kassa_view import h
        msg = (f"⚠️ <b>{h(p['name'])}</b>: {dm} — chek o'zgardi ({h(what)}), kun yopilgan. Kassani o'zingiz "
               "to'g'rilang (💵 Kassa → 📊 Hisobot → 📅 Kunlar).")
        await ctx.notifier._send_many(ctx.notifier.owner_ids(), msg)
        await note(ctx, chat_id, f"🔒 День {dm} закрыт — руководитель получил сообщение.", reply_to=mid)
        return
    pool = list(rows)
    for old_a, new_a in zip(rem, add):                     # summa o'zgardi
        hit = next((x for x in pool if x["amount"] == old_a), None)
        if hit is not None:
            K.edit_check_amount(db, hit["id"], new_a)
            pool.remove(hit)
    for old_a in rem[len(add):]:                           # o'chirildi
        hit = next((x for x in pool if x["amount"] == old_a), None)
        if hit is not None:
            K.delete_check(db, hit["id"])
            pool.remove(hit)
    for new_a in add[len(rem):]:                           # qo'shildi
        K.add_check(db, p["id"], day, new_a)
    await note(ctx, chat_id, f"✅ Касса за {dm} исправлена: {what}", reply_to=mid)


def admin_person(ctx, uid: int | None, owner: bool):
    """Ega yoki admin ham RD da ishlasa — uning kassadagi yozuvi: egada — «👑 Bu menman» (self), boshqasida —
    Telegram ID si bog'langan xodim. Yo'q bo'lsa — None."""
    db = ctx.db
    if owner:
        me = db.one("SELECT * FROM people WHERE kassa_kind='self' AND active=1 ORDER BY id LIMIT 1")
        if me is not None:
            return me
    from . import people as P
    q = P.by_tg(db, uid) if uid else None
    return q if q is not None and q["active"] and q["kassa_kind"] else None


async def on_admin_message(ctx, message, p) -> bool:
    """Ega/admin panel chatida (egasi, 2026-11-04: «man ham RD da ishlayapman»): 🔗 havolali chek, ismsiz va «Rd» siz
    raqam («1950 10.09» — xodimdagidek), /gaz, javob qilib /delete, «Когда пришёл лид?» ga sana. Tepasida ism yoki
    «Rd» bilan yozilgan achot — avvalgidek to'g'ridan-to'g'ri kassa hisoboti (kassa_flow). -> ishlandimi."""
    text = message.text or message.caption or ""
    cmd = _cmd(text)
    if cmd in CMD_GAZ or LINK_RE.search(text):
        return await on_message(ctx, message, p)
    rt = getattr(message, "reply_to_message", None)
    if cmd in CMD_DEL and rt is not None and ctx.db.one(
            "SELECT 1 FROM wchecks WHERE chat_id=? AND msg_id=? AND person_id=?", (message.chat.id, rt.message_id, p["id"])):
        return await on_message(ctx, message, p)
    if DATE_ONLY.fullmatch(text):                          # bot so'ragan lid kuni
        return await on_lead_date(ctx, message, p)
    # ismsiz va «Rd» siz raqam («1950 10.09») — xodimdagidek chek (egasi, 2026-11-04). Tepasida ism («Adam» / o'z
    # nomi) yoki «Rd 04.11» bo'lsa — avvalgidek darhol o'sha akkauntga kassa hisoboti (kassa_flow)
    if not K.RD_FIND.search(text) and not K.split_tag(ctx.db, text)[2] and \
            parse(text, local_date(int(message.date.timestamp()), ctx.tz)):
        return await on_message(ctx, message, p)
    return False


async def on_edit(ctx, message, p, links_only: bool = False) -> None:
    """Xabar tahrirlandi: qayta o'qiladi; «✏️ Изменено: 2000 → 1970 ✅» / «✅ Принято» (5 daqiqada o'chadi)."""
    db = ctx.db
    chat_id, mid = message.chat.id, message.message_id
    old = db.all("SELECT * FROM wchecks WHERE chat_id=? AND msg_id=? AND person_id=? ORDER BY pos",
                 (chat_id, mid, p["id"]))
    sent_ts = int(message.date.timestamp())
    text = message.text or message.caption or ""
    if links_only and not old and not LINK_RE.search(text):
        return                                             # adminning oddiy (kassa hisoboti) xabari — tegilmaydi
    items = parse(text, local_date(sent_ts, ctx.tz))
    if not old and not items:
        return
    before = [x["amount"] for x in old if not x["deleted"]]
    reported = next((x["reported_ts"] for x in old if x["reported_ts"]), None)
    day_keep = next((x["day"] for x in old), None)          # kechagi (yoki tanlangan) kun — tahrirda o'zgarmaydi
    lead = next((x["lead_ts"] for x in old if x["lead_ts"]), None)        # xodim yozgan lid kuni qoladi
    ask = next((x["ask_mid"] for x in old if x["ask_mid"]), None)
    db.run("DELETE FROM wchecks WHERE chat_id=? AND msg_id=? AND person_id=?", (chat_id, mid, p["id"]))
    n, unknown, general = _store(ctx, p, chat_id, mid, sent_ts, items) if items else (0, 0, 0)
    if day_keep:
        db.run("UPDATE wchecks SET day=? WHERE chat_id=? AND msg_id=?", (day_keep, chat_id, mid))
    if reported:
        db.run("UPDATE wchecks SET reported_ts=? WHERE chat_id=? AND msg_id=?", (reported, chat_id, mid))
    if unknown and (lead or ask):
        db.run("UPDATE wchecks SET lead_ts=?, ask_mid=? WHERE chat_id=? AND msg_id=? AND topic_ts IS NULL "
               "AND lead_ts IS NULL", (lead, None if lead else ask, chat_id, mid))
    elif ask:                                              # endi topik topildi (yoki chek yo'q) — savol kerak emas
        await _drop_ask(ctx, chat_id, [{"ask_mid": ask}])
    after = [x["amount"] for x in db.all("SELECT amount FROM wchecks WHERE chat_id=? AND msg_id=? ORDER BY pos",
                                         (chat_id, mid))]
    if reported and before != after:                       # achotga kirgan edi — kassada ham to'g'rilanadi
        await kassa_sync(ctx, p, chat_id, mid, day_keep, before, after)
    if not n:
        if general:
            await react(ctx, chat_id, mid, "🧐", "🤨")
        else:
            await react(ctx, chat_id, mid, "👎")
            await note(ctx, chat_id, "❌ Не принято — сумма не найдена.", reply_to=mid)
        return
    await react(ctx, chat_id, mid, "🧐" if general else "👍", "🤨" if general else "")
    if before and before != after:
        txt = f"✏️ Изменено: {' '.join(map(str, before))} → {' '.join(map(str, after))} ✅"
    else:
        txt = "✅ Принято"
    await note(ctx, chat_id, txt, reply_to=mid)
    if unknown and not (lead or ask):
        await ask_lead(ctx, chat_id, mid, p["id"], ASK if any(it["chat"] for it in items) else ASK_PLAIN)


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
    # 3 soat ichidagi yangi chek — «за какой день?»; achot kuni — achotdagi oxirgi kun (yarim tundan keyin /gaz
    # qilsa ham kechagi ish uchun — o'sha kun)
    db.set(f"gaz:{p['id']}", f"{now}:{max(x['day'] for x in rows)}")
