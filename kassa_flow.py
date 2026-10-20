"""Kassa hisobotlari oqimi: guruhdagi cheklar → hisobot; yetishmagan narsa (kimniki, sana, narx, kim ishlagan)
egasi/adminlardan tugma bilan so'raladi; jarima/bonus/avans guruhdan so'roqsiz yoziladi."""
from __future__ import annotations

import datetime as dt
import logging

from . import kassa as K
from . import people as P
from .kassa_view import h, money, num
from .timeutil import local_date
from .ui import kb

log = logging.getLogger("kassa_flow")


def L(ctx, uz: str, ru: str) -> str:
    return ru if ctx.lang() == "ru" else uz


def _who_can_see(ctx, pid) -> list[int]:
    """Ega va hamkor haqidagi narsa — faqat egalarga; qolgani — egalar va to'liq adminlarga."""
    p = P.person(ctx.db, pid) if pid else None
    if p is not None and p["kassa_kind"] in ("self", "partner"):
        return ctx.notifier.owner_ids()
    return ctx.notifier.staff_ids()


async def _send(ctx, ids, text, markup=None, key: str = ""):
    """Savol/xabar bir nechta odamga: key bilan — biri javob bersa, hammadagi nusxa o'chadi.
    text funksiya bo'lsa — har kimga o'z tilida quriladi: () -> (matn, tugmalar)."""
    await ctx.notifier.send_keyed(ids, text, markup, key=key)


# ───────────────────────── hisobot matni (guruhdan yoki botning o'ziga yozilgan)
def _poster(ctx, uid: int | None, staff: bool, is_owner: bool):
    db = ctx.db
    if is_owner:
        me = db.one("SELECT id FROM people WHERE kassa_kind='self' AND active=1 LIMIT 1")
        return me["id"] if me else None
    if uid and not staff:
        p = P.by_tg(db, uid)
        if p is not None and p["kassa_kind"]:
            return p["id"]
    return None


def make_report(ctx, text: str, day: dt.date, chat_id: int, msg_id, uid: int | None, name: str, staff: bool,
                is_owner: bool) -> int | None:
    """Matndan hisobot yaratish (savolsiz). -> report id yoki None (hisobot emas)."""
    db = ctx.db
    tag, body, tag_name = K.split_tag(db, text)
    if not K.is_report_like(body):
        return None
    checks = K.report_checks(body, day, is_owner)
    if not checks:
        return None
    poster = _poster(ctx, uid, staff, is_owner)
    acct = tag or (None if tag_name else poster)
    rid = K.create_report(db, acct, chat_id, msg_id, uid, text, checks, name)
    if tag_name and not tag:
        db.run("UPDATE reports SET tag=? WHERE id=?", (tag_name, rid))
    if acct and poster and tag and poster != tag and not staff:
        K.set_pay_report(db, rid, poster)                   # xodim boshqa akkauntda ishlagan — zp unga
    return rid


async def on_group_text(ctx, message, text: str, staff: bool, uid: int | None, name: str) -> bool:
    """«Проёб» guruhidagi matn: jarima/bonus (faqat ega/admin) yoki cheklar. -> qayta ishlandimi."""
    db = ctx.db
    day = local_date(message.date.timestamp(), ctx.tz)
    edited = message.edit_date is not None
    if staff and K.has_kind(text):
        if edited:
            K.drop_adj_msg(db, message.chat.id, message.message_id)
        await record_adjustments(ctx, text, day, message.chat.id, message.message_id)
        return True
    is_owner = uid is not None and P.admin_level(db, ctx.cfg.owner_ids, uid) == "owner"
    rid = make_report(ctx, text, day, message.chat.id, message.message_id, uid, name, staff, is_owner)
    if rid is None:
        return False
    try:
        from aiogram.types import ReactionTypeEmoji
        await ctx.bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id,
                                           reaction=[ReactionTypeEmoji(emoji="👀")])
    except Exception:
        pass
    await advance(ctx, rid)
    return True


# ───────────────────────── botning o'ziga yozilgan hisobot / jarima (ega yoki admin)
async def private_entry(ctx, r, message):
    """Shaxsiy chatda: «Baxa\nrd 19.10\n1950 2600» yoki «@ivan штраф 5». -> panel (matn, tugmalar) yoki None."""
    from . import ui
    db = ctx.db
    text = r.text
    day = local_date(ctx.clock(), ctx.tz)
    if K.has_kind(text):
        items = K.parse_adjustments(db, text)
        if not items:
            return None
        await record_adjustments(ctx, text, day, r.chat_id, message.message_id)
        rows = db.all("SELECT * FROM adj WHERE chat_id=? AND msg_id=? AND pending=0", (r.chat_id, message.message_id))
        word = {"fine": L(ctx, "jarima", "штраф"), "bonus": L(ctx, "bonus", "бонус"), "adv": L(ctx, "avans", "аванс")}
        lines = [f"✍ {h(P.person(db, a['person_id'])['name'])}: {word.get(a['kind'], '?')} {money(a['usd'])} $"
                 for a in rows if a["person_id"]]
        if len(rows) < len(items):
            lines.append(L(ctx, "❓ Qolganlari bo'yicha savol pastda.", "❓ По остальным — вопрос ниже."))
        return ui.join(f"<b>✍ {L(ctx, 'YOZILDI', 'ЗАПИСАНО')}</b> · {day:%d.%m}", "", ui.card(lines)), \
            kb([(L(ctx, "⌂ Menyu", "⌂ Меню"), "m")])
    o = getattr(message, "forward_origin", None)
    if o is not None:                                       # xodimning hisoboti forward qilindi — o'shaniki
        u = getattr(o, "sender_user", None)
        fname = (" ".join(x for x in (u.first_name, u.last_name) if x) if u else
                 getattr(o, "sender_user_name", "") or "")
        fday = local_date(o.date.timestamp(), ctx.tz) if getattr(o, "date", None) else day
        rid = make_report(ctx, text, fday, r.chat_id, message.message_id, u.id if u else None, fname, False, False)
    else:
        rid = make_report(ctx, text, day, r.chat_id, message.message_id, r.uid, L(ctx, "siz", "вы"), True, r.owner)
    if rid is None:
        return None
    return report_panel(ctx, r, rid) or await report_done_panel(ctx, r, rid)


def report_panel(ctx, r, rid: int):
    """Panelda: navbatdagi savol yoki «✅ qabul qilindi»."""
    from . import ui
    ui.view(r, f"krv:{rid}")
    q = question(ctx, rid)
    if q is not None:
        text, markup, _ids = q
        return text, markup
    return None


async def report_done_panel(ctx, r, rid: int):
    from . import ui
    db = ctx.db
    rep = K.report(db, rid)
    if rep is None:
        return None
    if rep["status"] != "done":
        await finalize(ctx, rid)
    p = P.person(db, rep["person_id"])
    days = K.report_days(db, rid)
    rows = db.all("SELECT amount, usd FROM checks WHERE report_id=? AND skip=0", (rid,))
    usd = sum(x["usd"] or 0 for x in rows)
    lines = [f"🧾 <b>{h(p['name']) if p else '?'}</b> · {', '.join(d[8:10] + '.' + d[5:7] for d in days)}",
             f"{len(rows)} {L(ctx, 'chek', 'чек.')} · {num(sum(x['amount'] for x in rows))} · <b>{money(usd)} $</b>"]
    btn = [[(L(ctx, "📅 Kun", "📅 День"), f"kdd:{days[0]}") if days else None,
            (f"👤 {p['name']}", f"po:{p['id']}") if p else None],
           [(L(ctx, "↩️ Bekor qilish", "↩️ Отменить"), f"krm:{rid}")], [(L(ctx, "⌂ Menyu", "⌂ Меню"), "m")]]
    ui.view(r, f"krv:{rid}")
    return ui.join(f"<b>✅ {L(ctx, 'QABUL QILINDI', 'ПРИНЯТО')}</b>", "", ui.card(lines)), kb(*btn)


async def record_adjustments(ctx, text: str, day: dt.date, chat_id=None, msg_id=None) -> int:
    """«@bayzed штраф 5» → darhol shu kunga yoziladi. Tushunilmaganlari egasidan so'raladi."""
    db = ctx.db
    items = K.parse_adjustments(db, text)
    done = 0
    for it in items:
        if it["kind"] and it["person_id"]:
            K.add_adj(db, it["person_id"], it["kind"], it["usd"], day.isoformat(), source="group", note=text[:120],
                      chat_id=chat_id, msg_id=msg_id)
            done += 1
        else:
            aid = K.add_adj(db, it["person_id"], it["kind"], it["usd"], day.isoformat(), source="group",
                            note=text[:120], chat_id=chat_id, msg_id=msg_id, pending=1)
            await ask_adj(ctx, aid)
    if chat_id and msg_id and done:
        try:
            from aiogram.types import ReactionTypeEmoji
            await ctx.bot.set_message_reaction(chat_id=chat_id, message_id=msg_id,
                                               reaction=[ReactionTypeEmoji(emoji="✍")])
        except Exception:
            pass
    if not items:
        def build():
            return ("❓ " + h(text[:200]) + "\n\n" + L(ctx, "Jarima/bonus summasi topilmadi.", "Сумма штрафа/бонуса не найдена."),
                    kb([(L(ctx, "👌 Tushunarli", "👌 Понятно"), f"qn:adjmiss:{msg_id or 0}")]))
        await _send(ctx, ctx.notifier.staff_ids(), build, key=f"adjmiss:{msg_id or 0}")
    return done


async def ask_adj(ctx, aid: int) -> None:
    a = K.adj(ctx.db, aid)
    if a is None:
        return

    def build():
        word = {"fine": L(ctx, "jarima", "штраф"), "bonus": L(ctx, "bonus", "бонус"),
                "adv": L(ctx, "avans", "аванс")}.get(a["kind"], L(ctx, "jarima/bonus/avans", "штраф/бонус/аванс"))
        if a["person_id"] is None:
            btn = [[(p["name"], f"qa:{aid}:p:{p['id']}")] for p in P.people(ctx.db, kinds=("worker", "self", "partner"))]
            text = f"❓ <b>{L(ctx, 'Kimga', 'Кому')} {word} {money(a['usd'])} $?</b>\n<i>{h(a['note'])}</i>"
        else:
            btn = [[(L(ctx, "Jarima", "Штраф"), f"qa:{aid}:k:fine"), (L(ctx, "Bonus", "Бонус"), f"qa:{aid}:k:bonus"),
                    (L(ctx, "Avans", "Аванс"), f"qa:{aid}:k:adv")]]
            p = P.person(ctx.db, a["person_id"])
            text = f"❓ <b>{h(p['name'])}: {money(a['usd'])} $ — {L(ctx, 'nima?', 'что это?')}</b>\n<i>{h(a['note'])}</i>"
        btn.append([(L(ctx, "✖️ Bekor", "✖️ Отмена"), f"qa:{aid}:x:0")])
        return text, kb(*btn)
    await _send(ctx, _who_can_see(ctx, a["person_id"]), build, key=f"qa:{aid}")


# ───────────────────────── hisobotni yakunlash
def question(ctx, rid: int):
    """Hisobotga nima yetishmasa — savol: (matn, tugmalar, kimga) yoki None (tayyor)."""
    db = ctx.db
    r = K.report(db, rid)
    if r is None:
        return None
    need = K.report_needs(db, rid)
    if need is None:
        return None
    kind, arg = need
    snippet = h((r["raw"] or "")[:300])
    who = f"\n👤 {h(r['sender_name'])}" if r["sender_name"] else ""
    no = [(L(ctx, "🚫 Hisobot emas", "🚫 Не отчёт"), f"qr:{rid}:x:0")]
    if kind == "person":
        btn = [[(p["name"], f"qr:{rid}:p:{p['id']}")] for p in K.kassa_people(ctx.db)]
        new_name = r["tag"] or (r["sender_name"] if r["sender_id"] and not P.admin_level(
            db, ctx.cfg.owner_ids, r["sender_id"]) else "")
        if new_name:
            btn.insert(0, [(L(ctx, f"➕ Yangi xodim: {new_name}", f"➕ Новый сотрудник: {new_name}")[:60],
                            f"qr:{rid}:n:0")])
        btn.append(no)
        tag = f"\n🏷 {h(r['tag'])}" if r["tag"] else ""
        return (f"❓ <b>{L(ctx, 'Kimning hisoboti?', 'Чей отчёт?')}</b>{tag}{who}\n\n<code>{snippet}</code>", kb(*btn),
                ctx.notifier.staff_ids())
    p = P.person(db, r["person_id"])
    if kind == "date":
        t = local_date(ctx.clock(), ctx.tz)
        days = [t - dt.timedelta(days=i) for i in range(4)]
        btn = [[(d.strftime("%d.%m"), f"qr:{rid}:d:{d.isoformat()}") for d in days[:2]],
               [(d.strftime("%d.%m"), f"qr:{rid}:d:{d.isoformat()}") for d in days[2:]], no]
        return (f"❓ <b>{h(p['name'])}: {L(ctx, 'qaysi kun?', 'на какой день?')}</b>\n\n<code>{snippet}</code>", kb(*btn),
                _who_can_see(ctx, r["person_id"]))
    if kind == "price":
        btn = [[(L(ctx, "💲 Narx kiritish", "💲 Ввести цену"), f"qr:{rid}:$:{arg}")], no]
        return (f"❓ <b>{h(p['name'])}: {num(arg)} — {L(ctx, 'necha $?', 'сколько $?')}</b> "
                f"{L(ctx, 'Praysda yo‘q.', 'Нет в прайсе.')}\n\n<code>{snippet}</code>", kb(*btn),
                _who_can_see(ctx, r["person_id"]))
    days = ", ".join(d[8:10] + "." + d[5:7] for d in K.report_days(db, rid))
    btn = [[(o["name"], f"qr:{rid}:o:{o['id']}")] for o in K.kassa_people(db, kinds=("worker", "self"))] + [no]
    return (f"❓ <b>{h(p['name'])} ({days}) — {L(ctx, 'kim ishladi?', 'кто работал?')}</b>\n"
            f"{L(ctx, 'Zp o‘shanga, o‘z foizi bilan.', 'Зп получит он, по своему проценту.')}\n\n<code>{snippet}</code>",
            kb(*btn), ctx.notifier.staff_ids())


async def advance(ctx, rid: int) -> None:
    """Keyingi savolni yuborish (eski nusxalar o'chadi) yoki hisobotni yakunlash."""
    q = question(ctx, rid)
    if q is None:
        await ctx.notifier.resolve(f"qr:{rid}")
        await finalize(ctx, rid)
        return
    _text, _markup, ids = q
    await _send(ctx, ids, lambda: question(ctx, rid)[:2], key=f"qr:{rid}")


async def finalize(ctx, rid: int) -> None:
    db = ctx.db
    r = K.report(db, rid)
    if r is None or r["status"] == "done":
        return
    await ctx.notifier.resolve(f"qr:{rid}")                 # savol nusxalari chatlardan ketadi
    K.set_report_status(db, rid, "done")
    if r["chat_id"] and r["chat_id"] < 0 and r["msg_id"]:     # guruhda: 👀 → 👌 (hisobga olindi)
        try:
            from aiogram.types import ReactionTypeEmoji
            await ctx.bot.set_message_reaction(chat_id=r["chat_id"], message_id=r["msg_id"],
                                               reaction=[ReactionTypeEmoji(emoji="👌")])
        except Exception:
            pass
    pid = r["person_id"]
    p = P.person(db, pid)
    for n in K.supersede(db, rid):
        am = ", ".join(map(str, n["amounts"]))
        if n["kind"] == "replace":
            def build_rep(n=n, am=am):
                return (f"♻️ <b>{h(p['name'])}</b>: " + L(ctx, f"eski hisobot ({am}) yangisi bilan almashtirildi — "
                                                              "ikki marta sanalmaydi.",
                                                              f"старый отчёт ({am}) заменён новым — дважды не считается."),
                        kb([(L(ctx, "👌 To'g'ri", "👌 Верно"), f"qn:sup:{n['old']}"),
                            (L(ctx, "↩️ Eskisini qaytarish", "↩️ Вернуть старый"), f"qr:{n['old']}:r:0")]))
            await _send(ctx, _who_can_see(ctx, pid), build_rep, key=f"sup:{n['old']}")
        else:
            def build_dup(am=am):
                return (f"⚠️ <b>{h(p['name'])}</b>: {am} — " + L(ctx, "bu chek allaqachon bor. Takrormi?",
                                                                 "этот чек уже был. Повтор?"),
                        kb([(L(ctx, "Ha, yangisini olib tashlash", "Да, убрать новый"), f"qr:{rid}:u:0"),
                            (L(ctx, "Yo'q, ikkalasi to'g'ri", "Нет, оба верны"), f"qn:dup:{rid}")]))
            await _send(ctx, _who_can_see(ctx, pid), build_dup, key=f"dup:{rid}")
    shut = [d for d in K.report_days(db, rid) if K.is_closed(db, d)]
    if shut:
        await closed_day_alert(ctx, rid, shut)
    if db.get("kassa_notify") != "0":
        days = K.report_days(db, rid)
        rows = db.all("SELECT amount, usd FROM checks WHERE report_id=? AND skip=0", (rid,))
        usd = sum(x["usd"] or 0 for x in rows)
        text = (f"🧾 <b>{h(p['name'])}</b> · {', '.join(d[8:10] + '.' + d[5:7] for d in days)}\n"
                f"{len(rows)} {L(ctx, 'chek', 'чек.')} · {num(sum(x['amount'] for x in rows))} · <b>{money(usd)} $</b>")
        await _send(ctx, _who_can_see(ctx, pid), text, kb([(L(ctx, "👤 Kabinet", "👤 Кабинет"), f"po:{pid}")]),
                    key=f"kn:{rid}")


async def closed_day_alert(ctx, rid: int, days: list[str]) -> None:
    """Yopilgan kunga yangi (yoki tahrirlangan) hisobot keldi — faqat egaga, qolsinmi?"""
    db = ctx.db
    r = K.report(db, rid)
    p = P.person(db, r["person_id"]) if r else None
    if r is None or p is None:
        return
    rows = db.all("SELECT amount FROM checks WHERE report_id=? AND skip=0", (rid,))
    dd = ", ".join(d[8:10] + "." + d[5:7] for d in days)

    def build():
        text = (f"🔒 <b>{dd} — {L(ctx, 'kun yopilgan edi', 'день был закрыт')}</b>, "
                f"{L(ctx, 'lekin yangi hisobot keldi', 'но пришёл новый отчёт')}:\n"
                f"🧾 {h(p['name'])} · {len(rows)} {L(ctx, 'chek', 'чек.')} · <b>{num(sum(x['amount'] for x in rows))}</b>"
                f"\n{L(ctx, 'Hisobga qo‘shildi.', 'Добавлен в расчёт.')}")
        return text, kb([(L(ctx, "✅ Qolsin", "✅ Оставить"), f"kcl:{rid}:k"),
                         (L(ctx, "🚫 Hisobga olinmasin", "🚫 Не учитывать"), f"kcl:{rid}:x")],
                        [(L(ctx, "📅 Kunni ochish", "📅 Открыть день"), f"kdd:{days[0]}")])
    await _send(ctx, ctx.notifier.owner_ids(), build, key=f"kcl:{rid}")


async def ask_unassigned(ctx) -> None:
    db = ctx.db
    for pool in K.kassa_people(db, active_only=False, kinds=("pool",)):
        for d in K.unassigned_days(db, pool["id"]):
            btn = [[(o["name"], f"qp:{pool['id']}:{d}:{o['id']}")] for o in K.kassa_people(db, kinds=("worker", "self"))]

            def build(pool=pool, d=d, btn=btn):
                return (f"❓ <b>{h(pool['name'])} {d[8:10]}.{d[5:7]} — {L(ctx, 'kim ishladi?', 'кто работал?')}</b>",
                        kb(*btn))
            await _send(ctx, ctx.notifier.staff_ids(), build, key=f"qp:{pool['id']}:{d}")


async def repeat_questions(ctx) -> int:
    n = 0
    for rid in K.pending_reports(ctx.db):
        await advance(ctx, rid)
        n += 1
    for a in ctx.db.all("SELECT id FROM adj WHERE pending=1"):
        await ask_adj(ctx, a["id"])
        n += 1
    await ask_unassigned(ctx)
    return n
