"""Admin bo'lmaganlar bilan shaxsiy chat.

Xodim: zp sini bot orqali ko'rmaydi (egasi, 2026-11-04) — faqat 🔗 cheklar va /gaz achoti (wchecks.py); /start —
faqat qisqa yo'riqnoma (tugmasiz, ID siz).
Begona (bot tanimaydigan akkaunt): nima yozsa ham faqat «Бот сейчас не работает.» (xavfsizlik, egasi 2026-11-04).
To'g'ri kod yozsa (🔒 qulf kodi yoki 🔐 tiklash kodi) — 👑 ega bo'ladi va panel ochiladi; kod xabari darhol o'chadi.
Kod tanlashga urinish cheklangan: bir odamga kuniga 5 ta, hammaga 20 ta; yangi ega kirganda boshqa egalarga xabar.
Xodim xabarlari matni saqlanmaydi. Istisno — 🔗 chek (topik havolasi + summa), /delete va /gaz (wchecks.py):
bulardan ham faqat summa, topik raqami va vaqt olinadi.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
import time

from . import kassa as K
from . import people as P
from . import ui
from .kassa_view import label as plabel, worker_message
from .timeutil import local_date
from .ui import Req, card, h, kb, screen, title

log = logging.getLogger("private")

REQ_GAP = 600          # bitta odam 10 daqiqada bir marta so'rov yubora oladi
CODE_RE = re.compile(r"\S{4,32}")      # kodga o'xshaydi: bitta so'z, 4–32 belgi (boshqa matn urinish hisoblanmaydi)
CODE_USER_LIMIT = 5    # noto'g'ri kod: bir odamga kuniga
CODE_ALL_LIMIT = 20    # hammaga kuniga


def _name(user) -> str:
    return " ".join(x for x in (user.first_name, user.last_name) if x) or str(user.id)


def _person(ctx, user):
    return P.identify(ctx.db, user.id, user.username)


def _worker(ctx, user):
    p = _person(ctx, user) if user is not None else None
    return p if p is not None and p["active"] else None


def worker_screen(ctx, user) -> tuple[str, object]:
    """Xodimga — faqat qisqa yo'riqnoma (tugmasiz: zp ham, ID ham kerak emas — egasi, 2026-11-04)."""
    p = _worker(ctx, user)
    text = ui.join(f"<b>👋 {h(p['name']) if p else ''}</b>", "", card(
        ["🔗 Чек: ссылка на топик и под ней сумма — бот поставит 👍.",
         "Топика нет в наших RD — сумма и дата лида: 1950 10.09",
         "Ошибка — ответьте на чек /delete. Вечером /gaz — готовый отчёт для «Проёб»."]))
    return text, None


def _fails(db, key: str, day: str) -> int:
    v = db.get(key)
    d, _, n = v.partition(":")
    return int(n) if d == day and n.isdigit() else 0


async def try_code(ctx, user, chat_id: int, text: str) -> bool:
    """Begona to'g'ri kod yozdi (🔒 qulf kodi yoki 🔐 tiklash kodi) — 👑 ega, panel ochiladi. -> kirdimi."""
    from . import lock, recovery
    db = ctx.db
    text = (text or "").strip()
    if not CODE_RE.fullmatch(text):
        return False
    day = time.strftime("%Y-%m-%d")
    ukey, akey = f"code_fail:{user.id}", "code_fail:all"
    if _fails(db, ukey, day) >= CODE_USER_LIMIT or _fails(db, akey, day) >= CODE_ALL_LIMIT:
        return False                                       # bugun urinishlar tugadi — kod ham tekshirilmaydi
    how = ""
    if lock.is_set(db) and await asyncio.to_thread(lock.matches, db, text):
        how = "🔒 qulf kodi"
    elif recovery.is_set(db) and len(text) >= recovery.MIN_LEN and \
            await asyncio.to_thread(recovery.matches, db, text):
        how = "🔐 tiklash kodi"
        recovery.clear(db)                                 # tiklash kodi bir marta ishlaydi
    if not how:
        db.set(ukey, f"{day}:{_fails(db, ukey, day) + 1}")
        db.set(akey, f"{day}:{_fails(db, akey, day) + 1}")
        return False
    name = _name(user)
    P.set_admin(db, user.id, "owner", name)
    others = [o for o in ctx.notifier.owner_ids() if o != user.id]
    await ctx.notifier._send_many(others, f"🔐 <b>Yangi 👑 ega</b>: {h(name)} · <code>{user.id}</code> — {how} bilan "
                                          "kirdi. Bu siz bo'lmasangiz: ⚙️ → 👮 Adminlar → 🗑.")
    from .panel import main_menu, make_req
    req = make_req(ctx, user.id, chat_id, "m")
    t, mk = await main_menu(ctx, req)
    ui.HIST.pop(user.id, None)
    await ui.show(ctx.bot, chat_id, t, mk, fresh=True, view="m")
    return True


async def stranger(ctx, message) -> None:
    """Bot tanimaydigan akkaunt: faqat «Бот сейчас не работает.»; to'g'ri kod — 👑 ega (xabar darhol o'chadi)."""
    from . import lock
    text = (message.text or "").strip()
    if text.lower().startswith(("/ega", "/owner")):
        text = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
    elif text.startswith("/"):
        text = ""                                          # /start, /id … — kod urinishi emas (sanalmaydi)
    try:
        await message.delete()
    except Exception:
        pass
    if message.from_user is not None and await try_code(ctx, message.from_user, message.chat.id, text):
        return
    await lock.show_decoy(ctx, message.chat.id)


async def on_start(ctx, message) -> None:
    if _worker(ctx, message.from_user) is None:
        await stranger(ctx, message)
        return
    text, markup = worker_screen(ctx, message.from_user)
    await ui.show(ctx.bot, message.chat.id, text, markup, fresh=True)


async def on_text(ctx, message) -> None:
    """Matn saqlanmaydi va o'qilmaydi — faqat menyu qayta ko'rsatiladi. Xodimning 🔗 cheki (havola + summa),
    /delete va /gaz — wchecks (xabar chatda qoladi)."""
    if message.from_user is None:
        return
    p = _worker(ctx, message.from_user)
    if p is None:                                          # begona — «Бот сейчас не работает.» yoki kod
        await stranger(ctx, message)
        return
    from . import wchecks
    try:
        if await wchecks.on_message(ctx, message, p):
            return
    except Exception:
        log.exception("Xodim cheki")
    try:
        await message.delete()
    except Exception:
        pass
    text, markup = worker_screen(ctx, message.from_user)
    await ui.show(ctx.bot, message.chat.id, text, markup, fresh=True)


def _open_request(db, kind: str, tg_id: int):
    return db.one("SELECT * FROM requests WHERE kind=? AND tg_id=? AND status='open' ORDER BY id DESC LIMIT 1",
                  (kind, tg_id))


async def on_edit(ctx, message) -> None:
    """Xodim 🔗 chek xabarini tahrirladi — bot qayta o'qiydi (wchecks)."""
    if message.from_user is None:
        return
    p = _person(ctx, message.from_user)
    if p is None or not p["active"]:
        return
    from . import wchecks
    try:
        await wchecks.on_edit(ctx, message, p)
    except Exception:
        log.exception("Xodim cheki (tahrir)")


async def on_worker_cb(ctx, cb, data: str) -> None:
    """Eski xabardagi tugmalar («💰 Моя зарплата», «🆔 Мой ID», «📨 Запросить доступ») endi yo'q: xodimga —
    yo'riqnoma, begonaga — «Бот сейчас не работает.» (so'rov yuborilmaydi)."""
    user = cb.from_user
    chat_id = cb.message.chat.id
    p = _worker(ctx, user)
    if p is None:
        from . import lock
        await lock.show_decoy(ctx, chat_id)
        return
    if data.startswith("wd:"):                             # /gaz dan keyingi chek — qaysi kunga
        from . import wchecks
        await wchecks.on_day_cb(ctx, cb, data)
        return
    text, markup = worker_screen(ctx, user)
    await ui.show(ctx.bot, chat_id, text, markup, edit_id=cb.message.message_id)


async def notify_request(ctx, rid: int) -> None:
    db = ctx.db
    q = db.one("SELECT * FROM requests WHERE id=?", (rid,))

    def build():                                           # har egaga o'z tilida
        lang = ctx.lang()
        L = (lambda uz, ru: ru if lang == "ru" else uz)
        who = f"{h(q['name'])}" + (f" · @{h(q['arg'])}" if q["arg"] else "") + f" · <code>{q['tg_id']}</code>"
        if q["kind"] == "zp":
            p = P.by_tg(db, q["tg_id"])
            text = ui.join(f"<b>💰 {L('OYLIK SO‘ROVI', 'ЗАПРОС ЗАРПЛАТЫ')}</b>", "", card(
                [f"👤 {h(p['name']) if p else who}", L("Xodim o'z hisobini ko'rmoqchi. Yuborilsinmi?",
                                                       "Сотрудник хочет увидеть свой расчёт. Отправить?")]))
            markup = kb([(L("👀 Ko'rish", "👀 Посмотреть"), f"rq:{rid}:v")],
                        [(L("✅ Yuborish", "✅ Отправить"), f"rq:{rid}:y"), (L("✖️ Rad etish", "✖️ Отказать"),
                                                                            f"rq:{rid}:n")])
        else:
            text = ui.join(f"<b>📨 {L('KIRISH SO‘ROVI', 'ЗАПРОС ДОСТУПА')}</b>", "", card(
                [f"👤 {who}", L("Kim bu?", "Кто это?")]))
            markup = kb([(L("👤 Xodimga bog'lash", "👤 Привязать к сотруднику"), f"rq:{rid}:p")],
                        [(L("➕ Yangi xodim", "➕ Новый сотрудник"), f"rq:{rid}:new")],
                        [(L("👮 Admin (👁 ko'radi)", "👮 Админ (👁 просмотр)"), f"rq:{rid}:av"),
                         (L("👮 Admin (🛠 to'liq)", "👮 Админ (🛠 полный)"), f"rq:{rid}:af")],
                        [(L("💵 Faqat zp ko'radi", "💵 Только зп"), f"rq:{rid}:az")],
                        [(L("✖️ Rad etish", "✖️ Отказать"), f"rq:{rid}:n")])
        return text, markup
    await ctx.notifier.send_keyed(ctx.notifier.owner_ids(), build, key=f"rq:{rid}")


async def _tell(ctx, tg_id: int, text: str) -> bool:
    try:
        await ctx.bot.send_message(tg_id, text, parse_mode="HTML")
        return True
    except Exception as exc:
        log.info("Xodimga yuborilmadi %s: %s", tg_id, exc)
        return False


# ───────────────────────── ega so'rovni hal qiladi (panel ekrani)
@screen("rq", "owner")
async def request_screen(ctx, r: Req):
    """So'rov hal bo'lsa — boshqa egalardagi nusxasi o'chadi (bu xabar panelga aylanadi)."""
    rid = int(r.args[0])
    res = await _request_screen(ctx, r)
    q = ctx.db.one("SELECT status FROM requests WHERE id=?", (rid,))
    if q is None or q["status"] != "open":
        here = ((r.chat_id, getattr(r.message, "message_id", 0)),)
        await ctx.notifier.resolve(f"rq:{rid}", skip=here)
    return res


async def _request_screen(ctx, r: Req):
    db = ctx.db
    rid, op = int(r.args[0]), (r.args[1] if len(r.args) > 1 else "")
    q = db.one("SELECT * FROM requests WHERE id=?", (rid,))
    if q is None:
        return r.L("⚠️ So'rov topilmadi", "⚠️ Запрос не найден")
    if q["status"] != "open" and op != "v":
        done = {"done": r.L("✅ Hal qilingan", "✅ Решён"), "denied": r.L("✖️ Rad etilgan", "✖️ Отклонён"),
                "old": r.L("⌛ Eskirgan", "⌛ Устарел")}.get(q["status"], q["status"])
        return f"{title('📨', h(q['name']))}\n\n{card([done])}", kb(ui.nav(r))
    close = (lambda st="done": db.run("UPDATE requests SET status=? WHERE id=?", (st, rid)))
    if op == "n":
        close("denied")
        await _tell(ctx, q["tg_id"], "✖️ Запрос отклонён." if q["kind"] == "zp" else "✖️ Доступ не выдан.")
        return f"{title('✖️', r.L('RAD ETILDI', 'ОТКЛОНЕНО'))}\n\n{card([h(q['name'])])}", kb(ui.nav(r))
    if q["kind"] == "zp":
        p = P.by_tg(db, q["tg_id"])
        if p is None:
            close("old")
            return r.L("⚠️ Xodim topilmadi", "⚠️ Сотрудник не найден")
        today = local_date(ctx.clock(), ctx.tz)
        s, e = K.open_period(db, p["id"], today)
        zst = K.zp_state(db, s, e, today)
        if not zst["ready"]:
            note = r.L("🧮 Bu davr uchun zp hali hisoblanmagan. Avval haftani hisoblang, keyin yuboring.",
                       "🧮 Зп за этот период ещё не рассчитана. Сначала рассчитайте неделю, потом отправьте.") \
                if zst["mode"] == "button" else r.L("🧮 Zp hisoblash o'chiq — xodimga o'zingiz yozing.",
                                                     "🧮 Расчёт зп выключен — напишите сотруднику сами.")
            btn = [[(f"🧮 {plabel(x, x + dt.timedelta(days=6))}", f"kz:{x.isoformat()}")] for x in zst["weeks"]]
            return ui.join(title("🧮", h(p["name"])), "", card([note])), \
                kb(*btn, [(r.L("✖️ Rad etish", "✖️ Отказать"), f"rq:{rid}:n")], ui.nav(r))
        row = K.calc(db, s, e)["rows"].get(p["id"])
        from .score import person_line
        msg = (worker_message(row, s, e, person_line(ctx, p["id"], s, e)) if row
               else f"💰 Зарплата · {plabel(s, e)}\n\nНачислений нет.")
        if op == "v":
            return ui.join(title("👀", r.L("XODIM KO'RADIGAN MATN", "ЧТО УВИДИТ СОТРУДНИК"), h(p["name"])), "",
                           card([h(msg)])), \
                kb([(r.L("✅ Yuborish", "✅ Отправить"), f"rq:{rid}:y"), (r.L("✖️ Rad etish", "✖️ Отказать"),
                                                                        f"rq:{rid}:n")])
        if op == "y":
            ok = await _tell(ctx, q["tg_id"], h(msg))
            close()
            return ui.join(title("✅" if ok else "⚠️", r.L("YUBORILDI", "ОТПРАВЛЕНО") if ok else
                                 r.L("YUBORILMADI", "НЕ ОТПРАВЛЕНО"), h(p["name"]))), kb(ui.nav(r))
        return None
    # kirish so'rovi
    if op in ("av", "af", "az"):
        P.set_admin(db, q["tg_id"], {"av": "view", "af": "full", "az": "zp"}[op], q["name"])
        close()
        await _tell(ctx, q["tg_id"], "✅ Доступ выдан. Нажмите /menu")
        return ui.join(title("👮", r.L("ADMIN QO'SHILDI", "АДМИН ДОБАВЛЕН"), h(q["name"]))), kb(ui.nav(r))
    if op == "new":
        name = q["name"][:40]
        pid = P.add_person(db, name, q["arg"], q["tg_id"])
        close()
        await _tell(ctx, q["tg_id"], "✅ Вы добавлены как сотрудник. Нажмите /start")
        return ui.join(title("➕", r.L("XODIM QO'SHILDI", "СОТРУДНИК ДОБАВЛЕН"), h(name)), "", card(
            [r.L("Papka, foiz va boshqa sozlamalar — xodim kartasida.", "Папка, процент и прочее — в карточке.")])), \
            kb([(r.L("👤 Kartani ochish", "👤 Открыть карточку"), f"po:{pid}")], ui.nav(r))
    if op == "p":
        free = [p for p in P.people(db) if not p["tg_id"]]
        if not free:
            return r.L("ℹ️ Telegram'ga bog'lanmagan xodim yo'q", "ℹ️ Нет сотрудников без привязки")
        rows = ui.grid([(p["name"][:30], f"rq:{rid}:l:{p['id']}") for p in free])
        rows.append([(r.L("‹ Orqaga", "‹ Назад"), f"rq:{rid}:b")])
        return ui.join(title("👤", r.L("QAYSI XODIM?", "КАКОЙ СОТРУДНИК?"), h(q["name"]))), kb(*rows)
    if op == "l":
        pid = int(r.args[2])
        fields = {"tg_id": q["tg_id"]}
        if q["arg"]:
            fields["username"] = q["arg"]
        P.update_person(db, pid, **fields)
        close()
        await _tell(ctx, q["tg_id"], "✅ Доступ выдан. Нажмите /start")
        p = P.person(db, pid)
        return ui.join(title("🔗", r.L("BOG'LANDI", "ПРИВЯЗАНО"), h(p["name"]))), kb(
            [(r.L("👤 Kartani ochish", "👤 Открыть карточку"), f"po:{pid}")], ui.nav(r))
    # «orqaga» — so'rov kartasi qayta
    lang = r.lang
    L = (lambda uz, ru: ru if lang == "ru" else uz)
    who = f"{h(q['name'])}" + (f" · @{h(q['arg'])}" if q["arg"] else "") + f" · <code>{q['tg_id']}</code>"
    return ui.join(f"<b>📨 {L('KIRISH SO‘ROVI', 'ЗАПРОС ДОСТУПА')}</b>", "", card([f"👤 {who}"])), \
        kb([(L("👤 Xodimga bog'lash", "👤 Привязать к сотруднику"), f"rq:{rid}:p")],
           [(L("➕ Yangi xodim", "➕ Новый сотрудник"), f"rq:{rid}:new")],
           [(L("👮 Admin (👁)", "👮 Админ (👁)"), f"rq:{rid}:av"), (L("👮 Admin (🛠)", "👮 Админ (🛠)"), f"rq:{rid}:af")],
           [(L("💵 Faqat zp ko'radi", "💵 Только зп"), f"rq:{rid}:az")],
           [(L("✖️ Rad etish", "✖️ Отказать"), f"rq:{rid}:n")])
