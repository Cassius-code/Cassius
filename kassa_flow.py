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


async def _send(ctx, ids, text, markup=None):
    for uid in ids:
        try:
            await ctx.bot.send_message(uid, text, reply_markup=markup, parse_mode="HTML", disable_web_page_preview=True)
        except Exception as exc:
            log.info("Savol yuborilmadi %s: %s", uid, exc)


# ───────────────────────── guruhdagi xabar
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
    tag, body = K.split_tag(db, text)
    if not K.is_report_like(body):
        return False
    is_owner = uid is not None and P.admin_level(db, ctx.cfg.owner_ids, uid) == "owner"
    poster = None
    if is_owner:
        me = db.one("SELECT id FROM people WHERE kassa_kind='self' AND active=1 LIMIT 1")
        poster = me["id"] if me else None
    elif uid:
        p = P.by_tg(db, uid)
        if p is not None and p["kassa_kind"]:
            poster = p["id"]
    checks = K.report_checks(body, day, is_owner)
    if not checks:
        return False
    try:
        from aiogram.types import ReactionTypeEmoji
        await ctx.bot.set_message_reaction(chat_id=message.chat.id, message_id=message.message_id,
                                           reaction=[ReactionTypeEmoji(emoji="👀")])
    except Exception:
        pass
    acct = tag or poster
    rid = K.create_report(db, acct, message.chat.id, message.message_id, uid, text, checks, name)
    if acct and poster and tag and poster != tag:
        K.set_pay_report(db, rid, poster)                   # boshqa akkauntda ishlagan — zp unga
    await advance(ctx, rid)
    return True


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
        await _send(ctx, ctx.notifier.staff_ids(), "❓ " + h(text[:200]) + "\n\n" +
                    L(ctx, "Jarima/bonus summasi topilmadi.", "Сумма штрафа/бонуса не найдена."))
    return done


async def ask_adj(ctx, aid: int) -> None:
    a = K.adj(ctx.db, aid)
    if a is None:
        return
    word = {"fine": L(ctx, "jarima", "штраф"), "bonus": L(ctx, "bonus", "бонус"), "adv": L(ctx, "avans", "аванс")}.get(
        a["kind"], L(ctx, "jarima/bonus/avans", "штраф/бонус/аванс"))
    if a["person_id"] is None:
        btn = [[(p["name"], f"qa:{aid}:p:{p['id']}")] for p in P.people(ctx.db, kinds=("worker", "self", "partner"))]
        text = f"❓ <b>{L(ctx, 'Kimga', 'Кому')} {word} {money(a['usd'])} $?</b>\n<i>{h(a['note'])}</i>"
    else:
        btn = [[(L(ctx, "Jarima", "Штраф"), f"qa:{aid}:k:fine"), (L(ctx, "Bonus", "Бонус"), f"qa:{aid}:k:bonus"),
                (L(ctx, "Avans", "Аванс"), f"qa:{aid}:k:adv")]]
        p = P.person(ctx.db, a["person_id"])
        text = f"❓ <b>{h(p['name'])}: {money(a['usd'])} $ — {L(ctx, 'nima?', 'что это?')}</b>\n<i>{h(a['note'])}</i>"
    btn.append([(L(ctx, "✖️ Bekor", "✖️ Отмена"), f"qa:{aid}:x:0")])
    await _send(ctx, _who_can_see(ctx, a["person_id"]), text, kb(*btn))


# ───────────────────────── hisobotni yakunlash
async def advance(ctx, rid: int) -> None:
    db = ctx.db
    r = K.report(db, rid)
    if r is None:
        return
    need = K.report_needs(db, rid)
    if need is None:
        await finalize(ctx, rid)
        return
    kind, arg = need
    snippet = h((r["raw"] or "")[:300])
    who = f"\n👤 {h(r['sender_name'])}" if r["sender_name"] else ""
    if kind == "person":
        btn = [[(p["name"], f"qr:{rid}:p:{p['id']}")] for p in K.kassa_people(ctx.db)]
        btn.append([(L(ctx, "🚫 Hisobot emas", "🚫 Не отчёт"), f"qr:{rid}:x:0")])
        await _send(ctx, ctx.notifier.staff_ids(), f"❓ <b>{L(ctx, 'Kimning hisoboti?', 'Чей отчёт?')}</b>{who}\n\n<code>{snippet}</code>",
                    kb(*btn))
    elif kind == "date":
        t = local_date(ctx.clock(), ctx.tz)
        days = [t - dt.timedelta(days=i) for i in range(4)]
        btn = [[(d.strftime("%d.%m"), f"qr:{rid}:d:{d.isoformat()}") for d in days[:2]],
               [(d.strftime("%d.%m"), f"qr:{rid}:d:{d.isoformat()}") for d in days[2:]],
               [(L(ctx, "🚫 Hisobot emas", "🚫 Не отчёт"), f"qr:{rid}:x:0")]]
        p = P.person(db, r["person_id"])
        await _send(ctx, _who_can_see(ctx, r["person_id"]),
                    f"❓ <b>{h(p['name'])}: {L(ctx, 'qaysi kun?', 'на какой день?')}</b>\n\n<code>{snippet}</code>", kb(*btn))
    elif kind == "price":
        p = P.person(db, r["person_id"])
        btn = [[(L(ctx, "💲 Narx kiritish", "💲 Ввести цену"), f"qr:{rid}:$:{arg}")], [(L(ctx, "🚫 Hisobot emas", "🚫 Не отчёт"),
                                                                                f"qr:{rid}:x:0")]]
        await _send(ctx, _who_can_see(ctx, r["person_id"]),
                    f"❓ <b>{h(p['name'])}: {num(arg)} — {L(ctx, 'necha $?', 'сколько $?')}</b> {L(ctx, 'Praysda yo‘q.', 'Нет в прайсе.')}\n\n<code>{snippet}</code>",
                    kb(*btn))
    elif kind == "op":
        p = P.person(db, r["person_id"])
        days = ", ".join(d[8:10] + "." + d[5:7] for d in K.report_days(db, rid))
        btn = [[(o["name"], f"qr:{rid}:o:{o['id']}")] for o in K.kassa_people(db, kinds=("worker", "self"))]
        btn.append([(L(ctx, "🚫 Hisobot emas", "🚫 Не отчёт"), f"qr:{rid}:x:0")])
        await _send(ctx, ctx.notifier.staff_ids(), f"❓ <b>{h(p['name'])} ({days}) — {L(ctx, 'kim ishladi?', 'кто работал?')}</b>\n"
                                                  f"{L(ctx, 'Zp o‘shanga, o‘z foizi bilan.', 'Зп получит он, по своему проценту.')}\n\n<code>{snippet}</code>", kb(*btn))


async def finalize(ctx, rid: int) -> None:
    db = ctx.db
    r = K.report(db, rid)
    if r is None or r["status"] == "done":
        return
    K.set_report_status(db, rid, "done")
    pid = r["person_id"]
    p = P.person(db, pid)
    for n in K.supersede(db, rid):
        am = ", ".join(map(str, n["amounts"]))
        if n["kind"] == "replace":
            await _send(ctx, _who_can_see(ctx, pid), f"♻️ <b>{h(p['name'])}</b>: " + L(ctx, f"eski hisobot ({am}) yangisi bilan almashtirildi — "
                                                                       "ikki marta sanalmaydi.",
                                                                       f"старый отчёт ({am}) заменён новым — дважды "
                                                                       "не считается."),
                        kb([(L(ctx, "↩️ Eskisini qaytarish", "↩️ Вернуть старый"), f"qr:{n['old']}:r:0")]))
        else:
            await _send(ctx, _who_can_see(ctx, pid), f"⚠️ <b>{h(p['name'])}</b>: {am} — " + L(ctx, "bu chek allaqachon bor. Takrormi?",
                                                                          "этот чек уже был. Повтор?"),
                        kb([(L(ctx, "Ha, yangisini olib tashlash", "Да, убрать новый"), f"qr:{rid}:u:0"),
                            (L(ctx, "Yo'q, ikkalasi to'g'ri", "Нет, оба верны"), "qok")]))
    shut = [d for d in K.report_days(db, rid) if K.is_closed(db, d)]
    if shut:
        await closed_day_alert(ctx, rid, shut)
    if db.get("kassa_notify") != "0":
        days = K.report_days(db, rid)
        rows = db.all("SELECT amount, usd FROM checks WHERE report_id=? AND skip=0", (rid,))
        usd = sum(x["usd"] or 0 for x in rows)
        text = (f"🧾 <b>{h(p['name'])}</b> · {', '.join(d[8:10] + '.' + d[5:7] for d in days)}\n"
                f"{len(rows)} {L(ctx, 'chek', 'чек.')} · {num(sum(x['amount'] for x in rows))} · <b>{money(usd)} $</b>")
        await _send(ctx, _who_can_see(ctx, pid), text, kb([(L(ctx, "👤 Kabinet", "👤 Кабинет"), f"po:{pid}")]))


async def closed_day_alert(ctx, rid: int, days: list[str]) -> None:
    """Yopilgan kunga yangi (yoki tahrirlangan) hisobot keldi — faqat egaga, qolsinmi?"""
    db = ctx.db
    r = K.report(db, rid)
    p = P.person(db, r["person_id"]) if r else None
    if r is None or p is None:
        return
    rows = db.all("SELECT amount, usd FROM checks WHERE report_id=? AND skip=0", (rid,))
    usd = sum(x["usd"] or 0 for x in rows)
    dd = ", ".join(d[8:10] + "." + d[5:7] for d in days)
    text = (f"🔒 <b>{dd} — {L(ctx, 'kun yopilgan edi', 'день был закрыт')}</b>, "
            f"{L(ctx, 'lekin yangi hisobot keldi', 'но пришёл новый отчёт')}:\n"
            f"🧾 {h(p['name'])} · {len(rows)} {L(ctx, 'chek', 'чек.')} · {num(sum(x['amount'] for x in rows))} · "
            f"<b>{money(usd)} $</b>\n{L(ctx, 'Hisobga qo‘shildi.', 'Добавлен в расчёт.')}")
    await _send(ctx, ctx.notifier.owner_ids(), text,
                kb([(L(ctx, "✅ Qolsin", "✅ Оставить"), f"kcl:{rid}:k"),
                    (L(ctx, "🚫 Hisobga olinmasin", "🚫 Не учитывать"), f"kcl:{rid}:x")],
                   [(L(ctx, "📅 Kunni ochish", "📅 Открыть день"), f"kdd:{days[0]}")]))


async def ask_unassigned(ctx) -> None:
    db = ctx.db
    for pool in K.kassa_people(db, active_only=False, kinds=("pool",)):
        for d in K.unassigned_days(db, pool["id"]):
            btn = [[(o["name"], f"qp:{pool['id']}:{d}:{o['id']}")] for o in K.kassa_people(db, kinds=("worker", "self"))]
            await _send(ctx, ctx.notifier.staff_ids(),
                        f"❓ <b>{h(pool['name'])} {d[8:10]}.{d[5:7]} — {L(ctx, 'kim ishladi?', 'кто работал?')}</b>", kb(*btn))


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
