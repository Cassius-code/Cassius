"""Admin bo'lmaganlar bilan shaxsiy chat.

Xodim: «💰 Моя зарплата» — so'rov AVVAL egaga boradi, ega ✅ bossa xodimga faqat o'z zp/jarima/bonus/avansi yuboriladi.
Begona: «📨 Запросить доступ» — egaga so'rov (xodimga bog'lash / yangi xodim / admin / rad etish).
Xodim xabarlari matni saqlanmaydi.
"""
from __future__ import annotations

import datetime as dt
import logging
import time

from . import kassa as K
from . import people as P
from . import ui
from .kassa_view import label as plabel, worker_message
from .timeutil import local_date
from .ui import Req, card, h, kb, screen, title

log = logging.getLogger("private")

REQ_GAP = 600          # bitta odam 10 daqiqada bir marta so'rov yubora oladi


def _name(user) -> str:
    return " ".join(x for x in (user.first_name, user.last_name) if x) or str(user.id)


def _person(ctx, user):
    return P.identify(ctx.db, user.id, user.username)


def worker_screen(ctx, user) -> tuple[str, object]:
    p = _person(ctx, user)
    if p is not None and p["active"]:
        text = ui.join(f"<b>👋 {h(p['name'])}</b>", "", card(
            ["Здесь можно запросить расчёт зарплаты.", "Запрос сначала увидит руководитель."]))
        return text, kb([("💰 Моя зарплата", "w:zp")], [("🆔 Мой ID", "w:id")])
    text = ui.join("<b>🔒 RD CONTROL</b>", "", card(
        ["Бот только для сотрудников.", "Нажмите кнопку — руководитель получит запрос."]))
    return text, kb([("📨 Запросить доступ", "w:acc")], [("🆔 Мой ID", "w:id")])


async def on_start(ctx, message) -> None:
    text, markup = worker_screen(ctx, message.from_user)
    await ui.show(ctx.bot, message.chat.id, text, markup, fresh=True)


async def on_text(ctx, message) -> None:
    """Matn saqlanmaydi va o'qilmaydi — faqat menyu qayta ko'rsatiladi."""
    if message.from_user is None:
        return
    try:
        await message.delete()
    except Exception:
        pass
    text, markup = worker_screen(ctx, message.from_user)
    await ui.show(ctx.bot, message.chat.id, text, markup, fresh=True)


def _open_request(db, kind: str, tg_id: int):
    return db.one("SELECT * FROM requests WHERE kind=? AND tg_id=? AND status='open' ORDER BY id DESC LIMIT 1",
                  (kind, tg_id))


async def on_worker_cb(ctx, cb, data: str) -> None:
    db = ctx.db
    user = cb.from_user
    chat_id = cb.message.chat.id
    act = data.split(":")[1] if ":" in data else ""
    if act == "id":
        await ui.toast(ctx.bot, chat_id, f"🆔 <code>{user.id}</code>", 20)
        return
    if act not in ("zp", "acc"):
        text, markup = worker_screen(ctx, user)
        await ui.show(ctx.bot, chat_id, text, markup, edit_id=cb.message.message_id)
        return
    p = _person(ctx, user)
    kind = "zp" if act == "zp" and p is not None else "access"
    last = db.one("SELECT ts FROM requests WHERE kind=? AND tg_id=? ORDER BY id DESC LIMIT 1", (kind, user.id))
    if last is not None and time.time() - last["ts"] < REQ_GAP:
        await ui.toast(ctx.bot, chat_id, "⏳ Запрос уже отправлен. Ответ придёт сюда.", 6)
        return
    db.run("UPDATE requests SET status='old' WHERE kind=? AND tg_id=? AND status='open'", (kind, user.id))
    rid = int(db.run("INSERT INTO requests(kind, tg_id, name, arg, ts) VALUES(?,?,?,?,?)",
                     (kind, user.id, _name(user), P.norm_username(user.username), int(time.time()))).lastrowid)
    await notify_request(ctx, rid)
    await ui.show(ctx.bot, chat_id, ui.join("<b>⏳ Запрос отправлен</b>", "", card(
        ["Руководитель получил запрос.", "Ответ придёт в этот чат."])),
        kb([("‹ Назад", "w:menu")]), edit_id=cb.message.message_id)


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
    if op in ("av", "af"):
        P.set_admin(db, q["tg_id"], "view" if op == "av" else "full", q["name"])
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
           [(L("✖️ Rad etish", "✖️ Отказать"), f"rq:{rid}:n")])
