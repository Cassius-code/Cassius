"""🚨 Nazorat: zaderjka limiti, ish vaqti, stavka, papkalar (xodimlar va chatlar), kutayotganlar, lidni tekshirish."""
from __future__ import annotations

import csv
import io
from datetime import datetime

from . import people as P
from . import ui
from .links import message_link
from .timeutil import fmt, hhmm, parse_hhmm, parse_number
from .ui import Req, card, grid, h, kb, nav, on_input, onoff, screen, title, must

DEC_UZ = {"dup": "takror", "service": "xizmat xabari", "ours": "bizning Push", "excluded": "⚡/💊 — hisobga olinmaydi",
          "before": "kuzatuv boshlanishidan oldin", "stavka_skip": "stavka ketyapti — hisobga olinmaydi",
          "stavka_bet": "stavka videosi", "bet_text": "stavka matni", "stavka_end": "stavka tugadi",
          "auto_bet": "avtostavka videosi", "wait": "mijoz javob kutyapti", "wait_more": "mijoz yana yozdi",
          "wait_last": "mijoz ketma-ket yozdi — endi shu xabaridan hisoblanadi",
          "reply": "xodim javob berdi ✅", "staff": "xodim yozdi", "alert": "«задержка» yuborildi",
          "echo": "xodimdan keyin darhol bot xabari — mijoz emas", "night": "ish vaqtidan tashqari — hisoblanmaydi",
          "late_reply": "xodim javobi kech topildi ✅ — kutish javob paytida yopildi",
          "late_staff": "xodim yozdi (kech topildi)", "late_client": "mijoz yozdi (kech topildi)",
          "late_other": "kech topildi", "late_bet": "stavka videosi (kech topildi) — sanaldi"}
DEC_RU = {"dup": "повтор", "service": "служебное", "ours": "наш Пуш", "excluded": "⚡/💊 — не учитывается",
          "before": "до начала контроля", "stavka_skip": "идёт ставка — не учитывается", "stavka_bet": "кружок ставки",
          "bet_text": "текст ставки", "stavka_end": "ставка закончилась", "auto_bet": "автоставка",
          "wait": "клиент ждёт ответа", "wait_more": "клиент дописал",
          "wait_last": "клиент дописал подряд — считаем с этого сообщения", "reply": "сотрудник ответил ✅",
          "staff": "сотрудник написал", "alert": "«задержка» отправлена",
          "echo": "сразу после сотрудника сообщение бота — не клиент", "night": "вне рабочего времени — не считается",
          "late_reply": "ответ сотрудника найден позже ✅ — ожидание закрыто временем ответа",
          "late_staff": "сотрудник написал (найдено позже)", "late_client": "клиент написал (найдено позже)",
          "late_other": "найдено позже", "late_bet": "кружок ставки (найден позже) — засчитан"}
WHO_UZ = {"client": "mijoz (bot)", "staff": "xodim", "ours": "Push", "service": "xizmat", "": ""}
WHO_RU = {"client": "клиент (бот)", "staff": "сотрудник", "ours": "Пуш", "service": "служебное", "": ""}


def work_hours(ctx) -> str:
    return f"{ctx.db.get('work_start')}–{ctx.db.get('work_end')}"


def today_line(ctx, r: Req, fid: int) -> str:
    """«📅 Bugun — @baxa» (📅 Bugun kim qayerda bo'yicha)."""
    from . import roster as R
    from .timeutil import local_date
    t = local_date(ctx.clock(), ctx.tz)
    w = R.workers(ctx.db, fid, t)
    who = ", ".join(h(P.mention(p)) for p in w) or r.L("❗ hech kim", "❗ никого")
    extra = r.L(" (bugunga qo'yilgan)", " (на сегодня)") if R.override(ctx.db, fid, t) is not None else ""
    return f"📅 {r.L('Bugun', 'Сегодня')} — <b>{who}</b>{extra}"


@screen("c", "view")
async def control(ctx, r: Req):
    db = ctx.db
    need, remind, cap, window = ctx.tracker.stavka_limits()
    waiting = db.scalar("SELECT COUNT(*) FROM threads WHERE wait_since IS NOT NULL")
    group = db.get("proyob_group_id")
    lines = [f"🚨 {r.L('Zaderjka nazorati', 'Контроль задержек')} — {onoff(r, db.flag('delay_enabled'))}",
             f"⏱ {r.L('Limit', 'Лимит')} — <b>{db.get('limit_minutes')} {r.L('daq', 'мин')}</b>",
             slide_line(ctx, r),
             f"🕒 {r.L('Ish vaqti', 'Рабочее время')} — <b>{work_hours(ctx)}</b>",
             f"🎬 {r.L('Stavka', 'Ставка')} — {onoff(r, db.flag('stavka_enabled'))} · <b>{need}</b> "
             f"{r.L('video', 'кружка')}",
             f"⏳ {r.L('Hozir kutyapti', 'Сейчас ждут')} — <b>{waiting}</b>",
             f"📌 {r.L('«Проёб»da doska', 'Доска в «Проёб»')} — {onoff(r, db.flag('board_on'))}",
             nudge_line(ctx, r),
             clean_line(ctx, r),
             fine_line(ctx, r)]
    if not group:
        lines.append(r.L("⚠️ «Проёб» guruhi belgilanmagan (Sozlamalar)", "⚠️ Группа «Проёб» не задана (Настройки)"))
    text = ui.join(title("🚨", r.L("NAZORAT", "КОНТРОЛЬ")), "", card(lines),
                   r.L("<i>Mijoz = vositachi bot xabari. Javob = har qanday xodim xabari (papka akkauntidan ham). "
                       "Push xabari va xodim yozgan zahoti chiqqan bot xabari hisobga olinmaydi.</i>",
                       "<i>Клиент = сообщение бота-посредника. Ответ = сообщение любого сотрудника (и с аккаунта "
                       "папки). Пуш и сообщение бота сразу после сотрудника не считаются.</i>"))
    rows = []
    if r.can("full"):
        rows += grid([(f"⏱ {r.L('Limit', 'Лимит')}", "cl"), (f"🔁 {r.L('Ketma-ket', 'Подряд')}", "cv"),
                      (f"🕒 {r.L('Ish vaqti', 'Рабочее время')}", "ch"), (f"🎬 {r.L('Stavka', 'Ставка')}", "cs"),
                      (f"📁 {r.L('Papkalar', 'Папки')}", "cf")])
        rows.append([(f"💸 {r.L('Jarimalar', 'Штрафы')}", "cfn"), (f"📌 {r.L('Doska', 'Доска')}", "cpb")])
        rows.append([(f"🔔 {r.L('Eslatmalar', 'Напоминания')}", "cnr"),
                     (f"🧹 {r.L('Tozalash', 'Очистка')}", "ccl")])
    rows += grid([(f"⏳ {r.L('Kutayotganlar', 'Ожидают')}", "cw"), (f"🔍 {r.L('Lidni tekshirish', 'Проверить лид')}", "cc")])
    if r.can("full"):
        rows.append([((r.L("⛔ Zaderjkani o'chirish", "⛔ Выключить контроль") if db.flag("delay_enabled")
                       else r.L("✅ Zaderjkani yoqish", "✅ Включить контроль")), "ct")])
        rows.append([(f"🧾 {r.L('Qarorlar jurnali (fayl)', 'Журнал решений (файл)')}", "cj")])
    rows.append(nav(r))
    return text, kb(*rows)


def slide_line(ctx, r: Req) -> str:
    n = ctx.db.get_int("wait_slide_min", 5)
    if not n:
        return r.L("🔁 Ketma-ket yozsa — ⚪ o'chiq (birinchi xabaridan)", "🔁 Пишет подряд — ⚪ выкл (с первого сообщения)")
    return r.L(f"🔁 Ketma-ket yozsa — <b>{n} daq</b> ichidagi oxirgi xabaridan",
               f"🔁 Пишет подряд — с последнего сообщения в пределах <b>{n} мин</b>")


def _mins(r: Req, m: int) -> str:
    if m <= 0:
        return r.L("o'chmaydi", "не удаляются")
    if m % 60 == 0:
        return r.L(f"{m // 60} soat", f"{m // 60} ч")
    return r.L(f"{m} daq", f"{m} мин")


def nudge_line(ctx, r: Req) -> str:
    """🔔 Nazorat menyusida: jim yangi lid va to'lov eslatmasi."""
    n, p = ctx.db.get_int("newlead_quiet_min", 120), ctx.db.get_int("pay_remind_min", 15)
    off = r.L("o'chiq", "выкл")
    return (f"🔔 {r.L('Eslatmalar', 'Напоминания')} — 🆕 <b>{_mins(r, n) if n > 0 else off}</b> · "
            f"💳 <b>{_mins(r, p) if p > 0 else off}</b>")


@screen("cnr", "full")
async def nudges(ctx, r: Req):
    """🔔 Xodimlarga «Проёб»da eslatmalar: jim yangi lid va karta ketgandan keyingi jimlik (mijozga hech narsa)."""
    from .insights import NEWLEAD_CHOICES, PAY_CHOICES
    db = ctx.db
    if len(r.args) == 2 and r.args[0] in ("n", "p") and r.args[1].isdigit():
        v = int(r.args[1])
        if v in (NEWLEAD_CHOICES if r.args[0] == "n" else PAY_CHOICES):
            db.set("newlead_quiet_min" if r.args[0] == "n" else "pay_remind_min", str(v))
        ui.view(r, "cnr")
    n, p = db.get_int("newlead_quiet_min", 120), db.get_int("pay_remind_min", 15)
    off = r.L("O'chiq", "Выкл")
    lines = [r.L(f"🆕 <b>Yangi lid jim</b> — <b>{_mins(r, n) if n > 0 else off}</b>",
                 f"🆕 <b>Новый лид молчит</b> — <b>{_mins(r, n) if n > 0 else off}</b>"),
             r.L("<i>Bugun kelgan yangi lid: stavkadan keyin shuncha vaqt hech kim yozmasa (lid ham, xodim ham, Push "
                 "ham) — «Проёб»ga eslatma, o'sha kuni ishdagi xodimlar belgilanadi.</i>",
                 "<i>Новый лид за сегодня: после ставки столько времени никто не пишет (ни лид, ни сотрудник, ни "
                 "Пуш) — напоминание в «Проёб», отмечаются сотрудники смены.</i>"),
             "",
             r.L(f"💳 <b>To'lov eslatmasi</b> — <b>{_mins(r, p) if p > 0 else off}</b>",
                 f"💳 <b>Напоминание об оплате</b> — <b>{_mins(r, p) if p > 0 else off}</b>"),
             r.L("<i>Xodim kartani yubordi (/rek /dep /cash), keyin shuncha vaqt hech kim yozmadi — «Проёб»ga "
                 "eslatma, kartani yuborgan xodim belgilanadi. Mijozga hech narsa ketmaydi.</i>",
                 "<i>Сотрудник отправил карту (/rek /dep /cash), потом столько времени никто не пишет — "
                 "напоминание в «Проёб», отмечается тот, кто отправил карту. Клиенту ничего не уходит.</i>"),
             "",
             r.L("<i>Faqat ish vaqtida hisoblanadi. ⚡/💊 lidlar kirmaydi. Xabar 🧹 sozlamasiga ko'ra o'chadi.</i>",
                 "<i>Считается только рабочее время. ⚡/💊 лиды не входят. Сообщение удаляется по настройке 🧹.</i>")]
    row_n = [(("✅ " if n == v else "") + (_mins(r, v) if v else off), f"cnr:n:{v}") for v in NEWLEAD_CHOICES]
    row_p = [(("✅ " if p == v else "") + (_mins(r, v) if v else off), f"cnr:p:{v}") for v in PAY_CHOICES]
    return (ui.join(title("🔔", r.L("ESLATMALAR", "НАПОМИНАНИЯ")), "", card(lines),
                    f"<b>🆕 {r.L('Yangi lid jim:', 'Новый лид молчит:')}</b>"),
            kb(*grid(row_n, 3), [(f"— 💳 {r.L('To‘lov eslatmasi', 'Оплата')} —", "cnr")], *grid(row_p, 3),
               nav(r, "c")))


def clean_line(ctx, r: Req) -> str:
    from .tidy import minutes
    return (f"🧹 {r.L('Tozalash', 'Очистка')} — {r.L('zaderjka', 'задержки')}: <b>{_mins(r, minutes(ctx.db, 'delay'))}</b> · "
            f"{r.L('boshqalar', 'остальное')}: <b>{_mins(r, minutes(ctx.db, 'info'))}</b>")


@screen("ccl", "full")
async def clean_settings(ctx, r: Req):
    """🧹 «Проёб» toza tursin: botning o'z xabarlari qachon o'chadi (egasi boshqaradi)."""
    from .tidy import DELAY_CHOICES, INFO_CHOICES, minutes
    db = ctx.db
    if len(r.args) == 2 and r.args[0] in ("d", "i") and r.args[1].isdigit():
        v = int(r.args[1])
        if v in (DELAY_CHOICES if r.args[0] == "d" else INFO_CHOICES):
            db.set("clean_delay_min" if r.args[0] == "d" else "clean_info_min", str(v))
        ui.view(r, "ccl")
    d, i = minutes(db, "delay"), minutes(db, "info")
    lines = [r.L(f"🚨 Zaderjka xabari — xodim javob berganidan keyin: <b>{_mins(r, d)}</b>",
                 f"🚨 «Задержка» — после ответа сотрудника: <b>{_mins(r, d)}</b>"),
             r.L(f"📣 Boshqa xabarlar (soviyotgan va jim yangi lidlar, to'lov eslatmasi, kechikish, Push tugadi, "
                 f"jarima ogohlantirishi, stavka) — yozilganidan keyin: <b>{_mins(r, i)}</b>",
                 f"📣 Остальное («остывают», «новый лид», «карта отправлена», «Опоздание», «Пуш завершён», "
                 f"предупреждения, «ставка») — после отправки: <b>{_mins(r, i)}</b>"),
             r.L("💸 Jarima yozilgan xabar o'chmaydi — joyida qoladi.",
                 "💸 Сообщение со штрафом не удаляется — остаётся."),
             r.L("<i>Buyruq bilan chaqirilganlar (/topweek, /statistika …) va 📌 doska o'chmaydi. Hisob (kim javob berdi, "
                 "jarima) botda saqlanadi — faqat chatdagi xabar o'chadi. Botga guruhda «Xabarlarni o'chirish» huquqi "
                 "kerak.</i>",
                 "<i>Ответы на команды (/topweek, /statistika …) и 📌 доска не удаляются. Учёт (кто ответил, штрафы) "
                 "остаётся в боте — удаляется только сообщение в чате. Боту нужно право «Удалять сообщения».</i>")]
    row_d = [(("✅ " if d == v else "") + _mins(r, v), f"ccl:d:{v}") for v in DELAY_CHOICES]
    row_i = [(("✅ " if i == v else "") + _mins(r, v), f"ccl:i:{v}") for v in INFO_CHOICES]
    return (ui.join(title("🧹", r.L("«ПРОЁБ»NI TOZALASH", "ОЧИСТКА «ПРОЁБ»")), "", card(lines),
                    f"<b>{r.L('Zaderjka xabari:', 'Задержка:')}</b>"),
            kb(*grid(row_d, 3), [(f"— {r.L('Boshqa xabarlar', 'Остальное')} —", "ccl")], *grid(row_i, 3), nav(r, "c")))


REMIND_CHOICES = (3, 5, 10, 15, 20, 30)
GRACE_CHOICES = (3, 5, 10, 15)
LATE_CHOICES = (5, 10, 15, 20, 30)


def _ladder_words(r: Req, lad: list, kind: str) -> str:
    """«1-si 0 $, 2-si 5 $, keyingilari 20 $»."""
    from .fines import money
    if not lad:
        return r.L("summalar yozilmagan — jarimasiz", "суммы не заданы — без штрафа")
    parts = [r.L(f"{i}-si {money(v)} $", f"{i}-я {money(v)} $" if kind == "delay" else f"{i}-е {money(v)} $")
             for i, v in enumerate(lad, 1)]
    if len(lad) > 1:
        parts[-1] = r.L(f"{len(lad)}-si va keyingilari {money(lad[-1])} $",
                        (f"{len(lad)}-я и дальше {money(lad[-1])} $" if kind == "delay" else
                         f"{len(lad)}-е и дальше {money(lad[-1])} $"))
    else:
        parts = [r.L(f"har biri {money(lad[0])} $", f"каждая {money(lad[0])} $" if kind == "delay" else
                     f"каждое {money(lad[0])} $")]
    return ", ".join(parts)


def fine_parts(ctx, r: Req) -> list[tuple[str, str, str, bool]]:
    """Jarimalar: (belgi, nomi, summalar, ishlayaptimi)."""
    from . import fines
    off = r.L("o'chiq", "выкл")
    out = []
    lad = fines.ladder(ctx.db, "delay")
    ok = bool(lad) and ctx.db.flag("remind_on")
    out.append(("⏰", r.L("Zaderjka", "Задержка"), fines.ladder_text(lad, r.lang) if ok else off, ok))
    tbl = fines.late_table(ctx.db)                         # 🕘 kech qolish — daqiqa jadvali
    out.append(("🕘", r.L("Kech qolish", "Опоздание"), fines.late_table_text(tbl, r.lang) if tbl else off, bool(tbl)))
    return out


def fine_line(ctx, r: Req) -> str:
    """Nazorat menyusida bitta qator: jarimalar yoqiqmi va summalari."""
    if not ctx.db.flag("fines_enabled"):
        return f"💸 {r.L('Jarimalar', 'Штрафы')} — {onoff(r, False)}"
    parts = " · ".join(f"{icon} {amount}" for icon, _name, amount, _ok in fine_parts(ctx, r))
    return f"💸 {r.L('Jarimalar', 'Штрафы')} — {parts}"


@screen("cfn", "view")
async def fine_rules(ctx, r: Req):
    """💸 Jarimalar: zaderjka (har kuni noldan) va kech qolish (har hafta noldan) — egasi yozgan summalar bo'yicha."""
    from . import fines
    db = ctx.db
    if r.args and r.args[0] == "t" and r.can("full"):
        db.toggle("fines_enabled")
        ui.view(r, "cfn")
    on = db.flag("fines_enabled")
    _on, after, grace = ctx.tracker.alert_remind_rules()
    ep = db.get_int("fine_episode", 30)
    late = db.get_int("late_after_min", 15)
    d = r.L("daq", "мин")
    lines = [f"💸 {r.L('Avtomat jarimalar', 'Автоштрафы')} — {onoff(r, on)}", ""]
    lad = fines.ladder(db, "delay")
    lines += [f"⏰ <b>{r.L('Zaderjka', 'Задержка')}</b> — <b>{fines.ladder_text(lad, r.lang)}</b> "
              f"<i>({r.L('har kuni noldan', 'каждый день с нуля')})</i>",
              r.L(f"<i>«задержка» → {after // 60} {d} → eslatma → {grace // 60} {d} → javob bo'lmasa: 1 ta zaderjka. "
                  f"Bir vaqtda kechikkanlar va keyingi {ep} daqiqadagilari — o'sha 1 ta.</i>",
                  f"<i>«задержка» → {after // 60} {d} → напоминание → {grace // 60} {d} → нет ответа: 1 задержка. "
                  f"Задержавшиеся одновременно и в следующие {ep} мин — та же 1.</i>"), ""]
    tbl = fines.late_table(db)
    lines += [f"🕘 <b>{r.L('Kech qolish', 'Опоздание')}</b> — <b>{fines.late_table_text(tbl, r.lang)}</b> "
              f"<i>({r.L('necha daqiqa kech qolganiga qarab', 'по минутам опоздания')})</i>",
              r.L(f"<i>Ish boshlanishidan {late} daqiqa va ko'p kech kelsa — «Проёб»da xabar. Summa o'sha daqiqadan "
                  f"boshlab (jadvaldagi birinchisidan kam — 0 $). {late} daqiqadan kam — xabar ham, jarima ham yo'q.</i>",
                  f"<i>Опоздание на {late} мин и больше — сообщение в «Проёб». Сумма — с этой минуты (меньше первой "
                  f"строки — 0 $). Меньше {late} мин — ни сообщения, ни штрафа.</i>"), ""]
    lines.append(r.L("✍️ <b>Qo'lda</b> — «Проёб»da: <code>@xodim штраф 5</code>",
                     "✍️ <b>Вручную</b> — в «Проёб»: <code>@сотрудник штраф 5</code>"))
    note = [r.L("Kimga: o'sha kuni shu RD da ishlayotgan xodimga (📅 Bugun kim qayerda). Tanaffusdagisiga — yo'q.",
                "Кому: сотруднику, который сегодня работает в этой RD (📅 Кто где сегодня). На перерыве — нет."),
            r.L("Oxirgi summa keyingilarga ham. 0 — sanaladi, lekin pulsiz. Jarimalar o'chiq bo'lsa — hech narsa "
                "sanalmaydi va «штраф» so'zi chiqmaydi.",
                "Последняя сумма — и для следующих. 0 — считается, но без денег. Штрафы выключены — ничего не "
                "считается и слово «штраф» не пишется.")]
    rows = []
    if r.can("full"):
        rows.append([(f"⏰ {r.L('Zaderjka', 'Задержка')}", "crm"), (f"🕘 {r.L('Kech qolish', 'Опоздание')}", "cfl")])
    rows.append([(f"📋 {r.L('Bugun va shu hafta', 'Сегодня и неделя')}", "cfw")])
    if r.can("full"):
        rows.append([((r.L("⛔ Jarimalarni o'chirish", "⛔ Выключить штрафы") if on else
                       r.L("✅ Jarimalarni yoqish", "✅ Включить штрафы")), "cfn:t")])
    rows.append(nav(r, "c"))
    return ui.join(title("💸", r.L("JARIMALAR", "ШТРАФЫ")), "", card(lines), card(note)), kb(*rows)


@screen("cfw", "view")
async def fine_week(ctx, r: Req):
    """📋 Bugungi zaderjkalar va shu haftadagi kech qolishlar — har xodim, nechta va qancha."""
    from datetime import timedelta

    from . import fines
    from .timeutil import local_date
    t = local_date(ctx.clock(), ctx.tz)
    rows = fines.rows_for(ctx.db, t)
    show_money = r.can("full")
    lines = []
    for x in rows:
        bits = []
        if x["delay"]:
            bits.append(f"⏰ {x['delay']}" + (f" ({fines.money(x['usd_delay'])} $)" if show_money else ""))
        if x["late"]:
            bits.append(f"🕘 {x['late']}" + (f" ({fines.money(x['usd_late'])} $)" if show_money else ""))
        lines.append(f"<b>{h(x['p']['name'])}</b> — " + " · ".join(bits))
    mon = t - timedelta(days=t.weekday())
    sub = r.L(f"⏰ bugun {t:%d.%m} · 🕘 {mon:%d.%m} dan", f"⏰ сегодня {t:%d.%m} · 🕘 с {mon:%d.%m}")
    body = card(lines) if lines else r.L("<i>Hozircha hech kimda yo'q 👏</i>", "<i>Пока ни у кого нет 👏</i>")
    return ui.join(title("📋", r.L("ZADERJKA VA KECH QOLISH", "ЗАДЕРЖКИ И ОПОЗДАНИЯ"), sub), "", body), \
        kb(nav(r, "cfn"))


def remind_line(ctx, r: Req) -> str:
    on, after, grace = ctx.tracker.alert_remind_rules()
    if not on:
        return f"⏰ {r.L('Javobsiz zaderjka', 'Задержка без ответа')} — {onoff(r, False)}"
    return (f"⏰ {r.L('Javobsiz zaderjka', 'Задержка без ответа')} — "
            + r.L(f"{after // 60} daq → eslatma → {grace // 60} daq", f"{after // 60} мин → напоминание → {grace // 60} мин"))


@screen("crm", "full")
async def remind_screen(ctx, r: Req):
    """⏰ Zaderjka javobsiz qolsa: N daqiqada eslatma, muhlatda javob yo'q — 1 ta zaderjka (kunlik zinapoya)."""
    from . import fines
    db = ctx.db
    a = r.args
    if a and a[0] in ("on", "off"):
        db.set("remind_on", "1" if a[0] == "on" else "0")
        ui.view(r, "crm")
    elif len(a) == 2 and a[0] in ("r", "g") and a[1].isdigit():
        v = int(a[1])
        if v in (REMIND_CHOICES if a[0] == "r" else GRACE_CHOICES):
            db.set("remind_min" if a[0] == "r" else "remind_grace_min", str(v))
        ui.view(r, "crm")
    on, after, grace = ctx.tracker.alert_remind_rules()
    lad = fines.ladder(db, "delay")
    ep = db.get_int("fine_episode", 30)
    lines = [f"{r.L('Holat', 'Состояние')}: " + (r.L("🟢 <b>yoqiq</b>", "🟢 <b>включено</b>") if on else
                                                 r.L("⚪ o'chiq", "⚪ выключено")),
             r.L(f"1) «задержка» chiqqanidan <b>{after // 60} daqiqa</b> o'tib ham javob bo'lmasa — eslatma: o'sha "
                 "xabarga javob qilib, RD ning bugungi xodimi belgilanadi. Ish kuni tugaganda hali javobsiz bo'lsa — "
                 "darhol.",
                 f"1) Если через <b>{after // 60} мин</b> после «задержки» ответа нет — напоминание ответом на это "
                 "сообщение, с отметкой сегодняшнего сотрудника RD. Если рабочий день закончился — сразу."),
             r.L(f"2) Eslatmadan keyin <b>{grace // 60} daqiqa</b>da ham javob bo'lmasa — <b>1 ta zaderjka</b>.",
                 f"2) Если через <b>{grace // 60} мин</b> после напоминания ответа нет — <b>1 задержка</b>."),
             r.L(f"3) Summalar: <b>{_ladder_words(r, lad, 'delay')}</b>. Har kuni noldan.",
                 f"3) Суммы: <b>{_ladder_words(r, lad, 'delay')}</b>. Каждый день с нуля."),
             r.L(f"4) Bir vaqtda kechikkanlar va keyingi <b>{ep} daqiqa</b>dagilari — o'sha 1 ta zaderjka.",
                 f"4) Задержавшиеся одновременно и в следующие <b>{ep} мин</b> — та же 1 задержка."),
             r.L("<i>Eslatma paytida tanaffusdagi xodimga jarima yo'q. Matn: «💸 @xodim, вам штраф 10 $ за задержку "
                 "(2-я за сегодня)».</i>",
                 "<i>Кто на перерыве в момент напоминания — без штрафа. Текст: «💸 @сотрудник, вам штраф 10 $ за "
                 "задержку (2-я за сегодня)».</i>")]
    d = r.L("daq", "мин")
    row_r = [(("✅ " if after // 60 == v else "") + f"⏰ {v} {d}", f"crm:r:{v}") for v in REMIND_CHOICES]
    row_g = [(("✅ " if grace // 60 == v else "") + f"⏳ {v} {d}", f"crm:g:{v}") for v in GRACE_CHOICES]
    rows = grid(row_r, 3) + grid(row_g, 4)
    rows.append([(f"💸 {r.L('Summalar', 'Суммы')}: {fines.ladder_text(lad, r.lang)}", "cfi:fine_ladder_delay")])
    rows.append([(f"🔁 {ep} {d} — {r.L('bitta zaderjka', 'одна задержка')}", "cfi:fine_episode"),
                 ((r.L("⛔ O'chirish", "⛔ Выключить"), "crm:off") if on else (r.L("✅ Yoqish", "✅ Включить"), "crm:on"))])
    rows.append(nav(r, "cfn"))
    return ui.join(title("⏰", r.L("ZADERJKA", "ЗАДЕРЖКА")), "", card(lines),
                   r.L("<i>⏰ — eslatma qachon · ⏳ — eslatmadan keyin muhlat</i>",
                       "<i>⏰ — когда напомнить · ⏳ — срок после напоминания</i>")), kb(*rows)


def _late_ru(m: int) -> str:
    """«Проёб»dagidek: 40 → «40 мин», 60 → «1 ч», 90 → «1 ч 30 мин»."""
    hrs, mins = divmod(int(m), 60)
    return (f"{hrs} ч {mins:02d} мин" if mins else f"{hrs} ч") if hrs else f"{mins} мин"


@screen("cfl", "full")
async def fine_late(ctx, r: Req):
    """🕘 Kech qolish: necha daqiqadan «kech» va jarima jadvali — necha daqiqa kech qolganiga qarab (egasi yozadi)."""
    from . import fines
    db = ctx.db
    if len(r.args) == 2 and r.args[0] == "a" and r.args[1].isdigit() and int(r.args[1]) in LATE_CHOICES:
        db.set("late_after_min", r.args[1])
        ui.view(r, "cfl")
    tbl = fines.late_table(db)
    late = db.get_int("late_after_min", 15)
    d = r.L("daq", "мин")
    lines = [r.L(f"⏳ Kech hisoblanadi — <b>{late} daqiqa</b> va ko'p (kamiga — xabar ham, jarima ham yo'q)",
                 f"⏳ Опоздание — от <b>{late} мин</b> (меньше — ни сообщения, ни штрафа)")]
    if tbl:
        lines.append(r.L("💵 <b>Jarima — necha daqiqa kech qolganiga qarab:</b>",
                         "💵 <b>Штраф — по минутам опоздания:</b>"))
        if late < tbl[0][0]:
            lines.append(r.L(f"• {late}–{tbl[0][0] - 1} daq → 0 $ (faqat xabar)",
                             f"• {late}–{tbl[0][0] - 1} мин → 0 $ (только сообщение)"))
        lines += [r.L(f"• {fines.dur_text(m)} va ko'p → <b>{fines.money(v)} $</b>",
                      f"• от {fines.dur_text(m, 'ru')} → <b>{fines.money(v)} $</b>") for m, v in tbl]
        ex = tbl[0][0] + 5
        lines.append(r.L(f"<i>Summa o'sha daqiqadan boshlab: {fines.dur_text(ex)} → {fines.money(fines.late_amount(tbl, ex))} $."
                         "</i>",
                         f"<i>Сумма — с этой минуты: {fines.dur_text(ex, 'ru')} → "
                         f"{fines.money(fines.late_amount(tbl, ex))} $.</i>"))
    else:
        lines.append(r.L("💵 Jarima — <b>o'chiq</b> (jadval yozilmagan): kech qolganga faqat xabar.",
                         "💵 Штраф — <b>выкл</b> (таблица не задана): при опоздании только сообщение."))
    if not db.flag("fines_enabled"):
        lines.append(r.L("⚪ Avtomat jarimalar o'chiq — summa yozilmaydi (💸 Jarimalar → ✅ yoqish).",
                         "⚪ Автоштрафы выключены — сумма не пишется (💸 Штрафы → ✅ включить)."))
    lines.append(r.L("Ishga keldi = «Проёб»ga birinchi xabari (kechki kassa hisobotidan tashqari) yoki lidga birinchi "
                     "yozuvi. Dam olish kunida — kech qolish yo'q.",
                     "Пришёл = первое сообщение в «Проёб» (кроме вечернего отчёта кассы) или первое сообщение лиду. "
                     "В выходной опозданий нет."))
    m = tbl[min(1, len(tbl) - 1)][0] if tbl else late + 10
    usd = fines.late_amount(tbl, m) if db.flag("fines_enabled") else 0
    sample = f" — вам штраф {fines.money(usd)} $ (1-е опоздание за неделю)" if usd > 0 else (
        " (1-е опоздание за неделю, без штрафа)" if tbl and db.flag("fines_enabled") else "")
    note = [r.L("«Проёб»da:", "В «Проёб»:"), f"<i>🕘 @xodim, вы опоздали на {_late_ru(m)}{sample}</i>",
            r.L("<i>начало в … · по графику …</i> — mayda qator.", "<i>начало в … · по графику …</i> — мелкой строкой.")]
    row_a = [(("✅ " if late == v else "") + f"⏳ {v} {d}", f"cfl:a:{v}") for v in LATE_CHOICES]
    rows = [[(r.L("✏️ Jadvalni o'zgartirish", "✏️ Изменить таблицу"), "cfi:fine_late_table")]]
    rows += grid(row_a, 5)
    rows.append(nav(r, "cfn"))
    return ui.join(title("🕘", r.L("KECH QOLISH", "ОПОЗДАНИЕ")), "", card(lines), card(note)), kb(*rows)


FINE_KEYS = {"fine_episode": (0, 600), "fine_ladder_delay": None, "fine_late_table": None}


@screen("cfi", "full")
async def fine_rule_ask(ctx, r: Req):
    key = r.args[0] if r.args else ""
    if key not in FINE_KEYS:
        r.args = []
        return await fine_rules(ctx, r)
    back = "cfl" if key == "fine_late_table" else "crm"
    ui.ask(r, "fine_rule", back, key=key)
    ladder_help = r.L("Summalarni $ da, bo'sh joy bilan yuboring: 1-si, 2-si, 3-si … Oxirgisi keyingilarga ham.\n"
                      "Masalan: <code>0 5 10 20</code> — 1-si kechiriladi, 2-si 5 $, 3-si 10 $, 4- va keyingilari 20 $.\n"
                      "<code>5</code> — har biri 5 $. <code>0</code> — jarimasiz.",
                      "Пришлите суммы в $ через пробел: 1-я, 2-я, 3-я … Последняя — и для следующих.\n"
                      "Например: <code>0 5 10 20</code> — 1-я прощается, 2-я 5 $, 3-я 10 $, 4-я и дальше 20 $.\n"
                      "<code>5</code> — каждая 5 $. <code>0</code> — без штрафа.")
    prompts = {"fine_episode": r.L("Zaderjkadan keyin necha daqiqa ichidagi yangi kechikishlar o'sha 1 ta zaderjka "
                                   "hisoblansin? Masalan <code>30</code>. <code>0</code> — har biri alohida.",
                                   "Сколько минут после задержки новые задержки считать той же одной? Например "
                                   "<code>30</code>. <code>0</code> — каждая отдельно."),
               "fine_ladder_delay": r.L("<b>⏰ Zaderjka</b> (har kuni noldan).\n", "<b>⏰ Задержка</b> (каждый день с "
                                                                                 "нуля).\n") + ladder_help,
               "fine_late_table": r.L(
                   "<b>🕘 Kech qolish</b> — necha daqiqa kech qolsa, necha $.\n"
                   "Har qatorda: daqiqa — summa. Masalan:\n<code>30-10\n40-15\n60-25\n2ч-50</code>\n"
                   "Summa o'sha daqiqadan boshlab: 35 daq → 10 $, 50 daq → 15 $. Birinchisidan kam (masalan, "
                   "20 daq) — 0 $. Soatni <code>1ч</code>, <code>2ч</code> yoki daqiqada (<code>90</code>) yozing.\n"
                   "<code>0</code> — kech qolishga jarima yo'q.",
                   "<b>🕘 Опоздание</b> — сколько минут опоздал — сколько $.\n"
                   "В каждой строке: минуты — сумма. Например:\n<code>30-10\n40-15\n60-25\n2ч-50</code>\n"
                   "Сумма — с этой минуты: 35 мин → 10 $, 50 мин → 15 $. Меньше первой строки (например, "
                   "20 мин) — 0 $. Часы — <code>1ч</code>, <code>2ч</code> или в минутах (<code>90</code>).\n"
                   "<code>0</code> — без штрафа за опоздание.")}
    if key == "fine_late_table":                           # nusxa olib o'zgartirish oson bo'lsin — u yozgandek
        from . import fines
        cur = fines.late_table_input(fines.late_table(ctx.db)) or "0"
    else:
        cur = ctx.db.get(key) or ("—" if key != "fine_episode" else "0")
    return title("💸", r.L("JARIMA", "ШТРАФ")) + "\n\n" + card(
        [r.L(f"Hozir:\n<code>{h(cur)}</code>", f"Сейчас:\n<code>{h(cur)}</code>"), prompts[key]]), \
        ui.cancel_kb(r, back)


@on_input("fine_rule")
async def fine_rule_set(ctx, r: Req, key: str):
    from . import fines
    if key == "fine_late_table":                           # 🕘 «30-10 / 40-15 / 60-25 / 2ч-50»
        text = r.message.text if r.message is not None and getattr(r.message, "text", None) else r.text
        try:
            tbl = fines.parse_late_table(text)
        except ValueError as exc:
            bad = h(str(exc)) if str(exc) else ""
            return r.L(f"⚠️ Tushunmadim{f': «{bad}»' if bad else ''}. Har qatorda daqiqa va summa, masalan:\n"
                       "30-10\n40-15\n60-25\n2ч-50\n(10 qatorgacha, har daqiqa bir marta)",
                       f"⚠️ Не понял{f': «{bad}»' if bad else ''}. В каждой строке минуты и сумма, например:\n"
                       "30-10\n40-15\n60-25\n2ч-50\n(до 10 строк, каждая минута один раз)")
        ctx.db.set(key, fines.late_table_raw(tbl))
        r.args = []
        ui.view(r, "cfl")
        return await fine_late(ctx, r)
    if key == "fine_ladder_delay":
        try:
            lad = fines.parse_ladder(r.text)
        except ValueError:
            return r.L("⚠️ Masalan: 0 5 10 20 (10 tagacha son)", "⚠️ Например: 0 5 10 20 (до 10 чисел)")
        ctx.db.set(key, fines.ladder_raw(lad))
        r.args = []
        ui.view(r, "crm")
        return await remind_screen(ctx, r)
    v = parse_number(r.text)
    lo, hi = FINE_KEYS[key]
    if v is None or not lo <= v <= hi or v != int(v):
        return r.L(f"⚠️ {lo} dan {hi} gacha son", f"⚠️ Число от {lo} до {hi}")
    ctx.db.set(key, str(int(v)))
    r.args = []
    ui.view(r, "crm")
    return await remind_screen(ctx, r)


@screen("cpb", "full")
async def board_toggle(ctx, r: Req):
    """📌 «Проёб» tepasida qadalgan «Задержки сейчас» (har RD) — yoqish / o'chirish."""
    from . import board
    on = not ctx.db.flag("board_on")
    ctx.db.set("board_on", "1" if on else "0")
    try:
        if on:
            await board.refresh(ctx, int(ctx.clock()), force=True)
        else:
            await board.remove(ctx)
    except Exception:
        pass
    ui.view(r, "c")
    return await control(ctx, r)


@screen("cv", "full")
async def slide(ctx, r: Req):
    """Mijoz bir necha xabarni ketma-ket yozsa: birinchisidan N daqiqa ichidagi oxirgi xabaridan hisoblanadi."""
    if r.args and r.args[0].isdigit() and int(r.args[0]) in (0, 2, 3, 4, 5, 7, 10):
        ctx.db.set("wait_slide_min", r.args[0])
        r.args = []
        ui.view(r, "c")
        return await control(ctx, r)
    cur = ctx.db.get_int("wait_slide_min", 5)
    lines = [r.L("Mijoz yozdi va bir necha daqiqada yana yozdi — zaderjka <b>oxirgi</b> xabaridan hisoblanadi.",
                 "Клиент написал и через пару минут дописал — задержка считается с <b>последнего</b> сообщения."),
             r.L(f"Masalan, 5 daqiqa: 12:00 «salom», 12:04 «karta bering» → {ctx.db.get('limit_minutes')} daqiqa "
                 "12:04 dan hisoblanadi.",
                 f"Например, 5 минут: 12:00 «привет», 12:04 «дайте карту» → {ctx.db.get('limit_minutes')} минут "
                 "считаются с 12:04."),
             r.L("Birinchi xabaridan necha daqiqa ichidagi xabarlar hisobga olinsin?",
                 "Сколько минут от первого сообщения учитывать?")]
    d = r.L("daq", "мин")
    opts = [(("✅ " if cur == v else "") + (f"{v} {d}" if v else r.L("O'chiq", "Выкл")), f"cv:{v}")
            for v in (0, 3, 4, 5, 7, 10)]
    return ui.join(title("🔁", r.L("KETMA-KET XABARLAR", "СООБЩЕНИЯ ПОДРЯД")), "", card(lines)), \
        kb(*grid(opts, 3), nav(r, "c"))


@screen("ct", "full")
async def toggle_delay(ctx, r: Req):
    on = ctx.db.toggle("delay_enabled")
    if on:
        ctx.db.set("delay_from", str(int(ctx.clock())))     # yoqilgan paytdan: eski javobsizlar xabar chiqarmaydi
    return await control(ctx, r)


@screen("cl", "full")
async def ask_limit(ctx, r: Req):
    ui.ask(r, "limit", "c")
    return (title("⏱", r.L("JAVOB LIMITI", "ЛИМИТ ОТВЕТА")) + "\n\n" +
            card([r.L(f"Hozir: <b>{ctx.db.get('limit_minutes')} daqiqa</b>",
                      f"Сейчас: <b>{ctx.db.get('limit_minutes')} минут</b>"),
                  r.L("Necha daqiqada javob berilmasa «задержка» bo'lsin? Son yuboring (1–720).",
                      "Через сколько минут без ответа — «задержка»? Пришлите число (1–720).")]),
            ui.cancel_kb(r, "c"))


@on_input("limit")
async def set_limit(ctx, r: Req):
    v = parse_number(r.text)
    if v is None or not 1 <= v <= 720:
        return r.L("⚠️ 1 dan 720 gacha son yuboring", "⚠️ Пришлите число от 1 до 720")
    ctx.db.set("limit_minutes", str(int(v)))
    return await control(ctx, r)


@screen("ch", "full")
async def ask_hours(ctx, r: Req):
    ui.ask(r, "hours", "c")
    return (title("🕒", r.L("ISH VAQTI", "РАБОЧЕЕ ВРЕМЯ")) + "\n\n" +
            card([r.L(f"Hozir: <b>{work_hours(ctx)}</b>", f"Сейчас: <b>{work_hours(ctx)}</b>"),
                  r.L("Boshlanish va tugashni yuboring, masalan <code>10:00-23:00</code>.\n"
                      "Boshlanish vaqti — «доброе утро» uchun ham (kech qolish).",
                      "Пришлите начало и конец, например <code>10:00-23:00</code>.\n"
                      "Начало — и для «доброе утро» (опоздания).")]),
            ui.cancel_kb(r, "c"))


@on_input("hours")
async def set_hours(ctx, r: Req):
    import re
    parts = re.findall(r"\d{1,2}[:.]\d{2}", r.text)
    if len(parts) != 2:
        return r.L("⚠️ Ko'rinishi: 10:00-23:00", "⚠️ Формат: 10:00-23:00")
    try:
        a, b = parse_hhmm(parts[0]), parse_hhmm(parts[1])
    except ValueError:
        return r.L("⚠️ Vaqt noto'g'ri", "⚠️ Неверное время")
    if a >= b:
        return r.L("⚠️ Boshlanish tugashdan oldin bo'lsin", "⚠️ Начало должно быть раньше конца")
    ctx.db.set("work_start", hhmm(a))
    ctx.db.set("work_end", hhmm(b))
    return await control(ctx, r)


# ───────────────────────── stavka
@screen("cs", "full")
async def stavka(ctx, r: Req):
    db = ctx.db
    need, _next, _late, _window = ctx.tracker.stavka_limits()
    first, nxt, max_n = ctx.tracker.remind_rules()
    limit = ctx.tracker.remind_limit()
    running = db.scalar("SELECT COUNT(*) FROM threads WHERE stavka='on'")
    d = r.L("daq", "мин")
    text = ui.join(
        title("🎬", r.L("STAVKA (YANGI LID)", "СТАВКА (НОВЫЙ ЛИД)")), "",
        card([f"{r.L('Holat', 'Состояние')} — {onoff(r, db.flag('stavka_enabled'))}",
              f"🎬 {r.L('Tugashi', 'Завершение')} — <b>{need}</b> {r.L('ta stavka (dumaloq video)', 'ставки (кружка)')}",
              f"⏱ {r.L('1-stavka kutiladi', 'Первая ставка ждём')} — <b>{first // 60} {d}</b>",
              f"⏱ {r.L('Keyingilari', 'Следующие')} — <b>{nxt // 60} {d}</b> {r.L('oldingisidan', 'после предыдущей')}",
              f"🔔 {r.L('Eslatma', 'Напоминаний')} — <b>{max_n}</b> {r.L('martagacha', 'максимум')}",
              f"{r.L('Hozir stavkada', 'Сейчас в ставке')} — <b>{running}</b>"]),
        card([r.L(f"Yangi chat → stavka. Stavka = dumaloq video (vositachi bot tashlaydi; tushmasa xodim o'zi "
                  f"yuboradi — u ham sanaladi). {first // 60} daqiqada birinchisi, keyin har {nxt // 60} daqiqada "
                  f"keyingisi kelmasa «ставка» eslatiladi. {need} ta stavka kelsa — stavka tugaydi. Kelmasa — "
                  f"{limit}-eslatmadan keyin stavka tugaydi va keyingi xabarlar oddiy zaderjka hisoblanadi. "
                  "Stavka paytida hech kimning xabari zaderjka hisoblanmaydi.",
                  f"Новый чат → ставка. Ставка = кружок (ставит бот-посредник; если нет — сотрудник сам, это тоже "
                  f"считается). Нет первой за {first // 60} мин или следующей за {nxt // 60} мин — напоминание "
                  f"«ставка». Пришли {need} ставки — ставка завершена. Не пришли — после {limit}-го напоминания "
                  "ставка завершается, дальше обычный контроль задержек. Во время ставки сообщения не считаются "
                  "задержкой.")]))
    rows = [[((r.L("⛔ O'chirish", "⛔ Выключить") if db.flag("stavka_enabled") else r.L("✅ Yoqish", "✅ Включить")),
              "cst")],
            [(r.L("✏️ Sonlarni o'zgartirish", "✏️ Изменить числа"), "csn")], nav(r, "c")]
    return text, kb(*rows)


@screen("cst", "full")
async def stavka_toggle(ctx, r: Req):
    ctx.db.toggle("stavka_enabled")
    return await stavka(ctx, r)


STAVKA_KEYS = (("stavka_count", 1, 20), ("stavka_first", 1, 180), ("stavka_next", 1, 180),
               ("stavka_max_remind", 0, 10))


@screen("csn", "full")
async def stavka_ask(ctx, r: Req):
    ui.ask(r, "stavka", "cs")
    now = " ".join(ctx.db.get(k) for k, _lo, _hi in STAVKA_KEYS)
    return (title("🎬", r.L("STAVKA SONLARI", "ЧИСЛА СТАВКИ")) + "\n\n" +
            card([r.L(f"Hozir: <code>{now}</code>", f"Сейчас: <code>{now}</code>"),
                  r.L("4 ta son yuboring, masalan <code>3 20 20 3</code>:\n1) nechta stavka;\n"
                      "2) birinchisi necha daqiqada kelishi kerak;\n3) keyingisi oldingisidan necha daqiqada;\n"
                      "4) eslatma ko'pi bilan necha marta (shundan keyin stavka tugaydi).",
                      "Пришлите 4 числа, например <code>3 20 20 3</code>:\n1) сколько ставок;\n"
                      "2) за сколько минут первая;\n3) следующая после предыдущей — минут;\n"
                      "4) напоминаний максимум (после них ставка завершается).")]),
            ui.cancel_kb(r, "cs"))


@on_input("stavka")
async def stavka_set(ctx, r: Req):
    import re
    nums = [int(x) for x in re.findall(r"\d+", r.text)]
    if not 1 <= len(nums) <= len(STAVKA_KEYS) or any(not lo <= v <= hi for v, (_k, lo, hi) in zip(nums, STAVKA_KEYS)):
        return r.L("⚠️ Masalan: 3 20 20 3", "⚠️ Например: 3 20 20 3")
    for v, (k, _lo, _hi) in zip(nums, STAVKA_KEYS):
        ctx.db.set(k, str(v))
    return await stavka(ctx, r)


# ───────────────────────── kutayotganlar
@screen("cw", "view")
async def waiting(ctx, r: Req):
    db, now = ctx.db, int(ctx.clock())
    rows = db.all("SELECT * FROM threads WHERE wait_since IS NOT NULL ORDER BY wait_since LIMIT 25")
    folders = {f["id"]: f for f in P.folders(db)}
    lines = []
    for th in rows:
        fid = ctx.tracker.chat_folder.get(th["chat_id"])
        mins = ctx.tracker.elapsed(fid, th["wait_since"], now) // 60 if fid else 0
        link = message_link(th["chat_id"], th["wait_msg_id"] or th["topic_id"], th["topic_id"])
        lab = h(ctx.tracker.label(th["chat_id"], th["topic_id"])[:24] or th["topic_id"])
        mark = "🚨" if th["alert_id"] else "⏳"
        fname = h(folders[fid]["name"]) if fid in folders else ""
        lines.append(f"{mark} <a href=\"{link}\">{lab}</a> · {fname} · <b>{mins} {r.L('daq', 'мин')}</b>")
    body = card(lines) if lines else r.L("<i>Hozir hech kim javob kutmayapti 👏</i>", "<i>Сейчас никто не ждёт 👏</i>")
    return ui.join(title("⏳", r.L("JAVOB KUTAYOTGANLAR", "ЖДУТ ОТВЕТА"), r.L("ish vaqtidagi daqiqalar",
                                                                              "минуты рабочего времени")), "", body), \
        kb([(r.L("🔄 Yangilash", "🔄 Обновить"), "cw")], nav(r, "c"))


# ───────────────────────── lidni tekshirish
@screen("cc", "view")
async def check_ask(ctx, r: Req):
    ui.ask(r, "check", "c")
    return (title("🔍", r.L("LIDNI TEKSHIRISH", "ПРОВЕРКА ЛИДА")) + "\n\n" +
            card([r.L("Lid xabarining havolasini yuboring (topikda: xabarni bosib turing → «Havolani nusxalash»). "
                      "Bot nimani ko'rgani va nima qaror qilgani chiqadi.",
                      "Пришлите ссылку на сообщение лида (в топике: зажмите сообщение → «Копировать ссылку»). "
                      "Покажу, что бот видел и что решил.")]), ui.cancel_kb(r, "c"))


@on_input("check", "view")
async def check_show(ctx, r: Req):
    from .links import parse_message_link
    got = parse_message_link(r.text)
    if got is None:
        return r.L("⚠️ Bu xabar havolasi emas", "⚠️ Это не ссылка на сообщение")
    chat_id, topic, _msg = got
    if not ctx.tracker.is_monitored(chat_id):
        return r.L("⚠️ Bu chat nazoratda emas (papkalarda yo'q)", "⚠️ Этот чат не под контролем")
    if chat_id in ctx.tracker.forums and topic <= 1:
        return r.L("⚠️ Topik ichidagi xabar havolasi kerak", "⚠️ Нужна ссылка на сообщение внутри топика")
    return lead_card(ctx, r, chat_id, topic)


def lead_card(ctx, r: Req, chat_id: int, topic: int):
    db, now, tz = ctx.db, int(ctx.clock()), ctx.tz
    th = ctx.tracker.thread(chat_id, topic)
    lab = ctx.tracker.label(chat_id, topic) or str(topic)
    fid = ctx.tracker.chat_folder.get(chat_id)
    f = P.folder(db, fid)
    lines = []
    if th is None:
        lines.append(r.L("Bot bu nitni hali ko'rmagan.", "Бот ещё не видел эту нить."))
    else:
        need, _remind, _cap, _w = ctx.tracker.stavka_limits()
        if th["stavka"] == "on":
            lines.append(f"🎬 {r.L('Stavka ketyapti', 'Идёт ставка')}: <b>{th['bets']} / {need}</b> "
                         f"({r.L('boshlandi', 'началась')} {fmt(th['stavka_from'], tz)})")
        elif th["stavka"] == "done":
            lines.append(f"🎬 {r.L('Stavka tugadi', 'Ставка завершена')} {fmt(th['stavka_end'], tz)} · "
                         f"{r.L('video', 'кружков')} {th['bets']}")
        else:
            lines.append(f"🎬 {r.L('Stavka kuzatilmagan (eski lid)', 'Ставка не отслеживалась (старый лид)')}")
        if th["wait_since"] is not None:
            mins = ctx.tracker.elapsed(fid, th["wait_since"], now) // 60 if fid else 0
            lines.append(f"⏳ {r.L('Mijoz kutyapti', 'Клиент ждёт')} {fmt(th['wait_since'], tz)} · <b>{mins} "
                         f"{r.L('daq', 'мин')}</b>" + (" · 🚨" if th["alert_id"] else ""))
        else:
            lines.append(f"✅ {r.L('Hech kim javob kutmayapti', 'Ответа никто не ждёт')}")
    dec, who = (DEC_RU, WHO_RU) if r.lang == "ru" else (DEC_UZ, WHO_UZ)
    ev = []
    for j in reversed(db.all("SELECT * FROM journal WHERE chat_id=? AND topic_id=? ORDER BY id DESC LIMIT 12",
                             (chat_id, topic))):
        kind = "⭕" if j["kind"] == "video" else ""
        ev.append(f"{fmt(j['ts'], tz, '%H:%M:%S')} · {who.get(j['who'], j['who'])} {kind} → {dec.get(j['decision'], j['decision'])}")
    text = ui.join(title("🔍", h(lab[:40]), h(f["name"]) if f else ""), "", card(lines),
                   card([f"<b>{r.L('Bot nimani ko‘rdi', 'Что видел бот')}</b>"] + ev) if ev else "")
    return text, kb([(r.L("🔍 Boshqa lid", "🔍 Другой лид"), "cc")], nav(r, "c"))


# ───────────────────────── jurnal fayli
@screen("cj", "full")
async def journal_file(ctx, r: Req):
    db, tz, now = ctx.db, ctx.tz, int(ctx.clock())
    buf = io.StringIO()
    wr = csv.writer(buf)
    dec = DEC_RU if r.lang == "ru" else DEC_UZ
    wr.writerow(["time", "decided", "link", "chat", "topic", "msg", "sender", "who", "kind", "source", "decision",
                 "meaning"])
    titles = {c["chat_id"]: c["title"] for c in db.all("SELECT chat_id, title FROM chats")}
    for j in db.all("SELECT * FROM journal WHERE at>=? ORDER BY id", (now - 86400,)):
        link = message_link(j["chat_id"], j["msg_id"], j["topic_id"]) if j["msg_id"] else ""
        wr.writerow([fmt(j["ts"], tz, "%d.%m.%Y %H:%M:%S"), fmt(j["at"], tz, "%d.%m.%Y %H:%M:%S"), link,
                     titles.get(j["chat_id"], j["chat_id"]), j["topic_id"], j["msg_id"] or "", j["sender_id"] or "",
                     j["who"], j["kind"], j["source"], j["decision"], dec.get(j["decision"], "")])
    stamp = datetime.fromtimestamp(now, tz).strftime("%Y-%m-%d_%H%M")
    await ctx.notifier.send_document(r.chat_id, ("﻿" + buf.getvalue()).encode("utf-8"), f"journal_{stamp}.csv",
                                     r.L("🧾 Bot qarorlari, 24 soat (xabar matnisiz).",
                                         "🧾 Решения бота за 24 часа (без текста сообщений)."))
    return await control(ctx, r)


# ───────────────────────── papkalar
def folder_leads(ctx, fid: int) -> dict:
    """Papkadagi lidlar. total — hammasi (forum topiklari + oddiy chatlar, Telegram'dagidek);
    all — Push bazasi: baza sanasidan keyin o'zi yozganlar (yangi ham, eski ham);
    week, today — bazadagilardan shu vaqtda o'zi yozganlar."""
    from .timeutil import day_start
    db, now = ctx.db, int(ctx.clock())
    base = ctx.pusher.base_from() if ctx.pusher else 0
    from .push import base_count
    total = db.scalar("SELECT COUNT(*) FROM topics t JOIN chats c ON c.chat_id=t.chat_id "
                      "WHERE c.folder_id=? AND t.topic_id<>1", (fid,)) + \
        db.scalar("SELECT COUNT(*) FROM chats c WHERE c.folder_id=? AND c.is_forum=0 "
                  "AND NOT EXISTS (SELECT 1 FROM topics t WHERE t.chat_id=c.chat_id)", (fid,))
    from .reports import new_leads_in
    d0 = day_start(now, ctx.tz)
    return {"total": total, "all": base_count(db, base, fid), "week": base_count(db, base, fid, now - 7 * 86400),
            "today": base_count(db, base, fid, d0), "new": new_leads_in(db, fid, d0, now + 1)}


def _fkey_hash(title: str) -> str:
    import hashlib
    from .userbot import folder_key
    return hashlib.sha1(folder_key(title).encode()).hexdigest()[:12]


async def _tg_folders(ctx) -> list[str]:
    import asyncio
    ub = ctx.userbot
    if ub is None:
        return []
    try:
        return await asyncio.wait_for(ub.folder_titles(), 10)
    except Exception:
        return list(getattr(ub, "tg_folders", []))


@screen("cf", "full")
async def folders(ctx, r: Req):
    """Asosiy akkauntdagi Telegram papkalari: ➕ bosib qo'shiladi (chatlari o'zi keladi), ✅ — ochiladi."""
    from .userbot import folder_key
    db = ctx.db
    online = ctx.userbot is not None and ctx.userbot.state == "online"
    tg = await _tg_folders(ctx)
    mine = {folder_key(f["name"]): f for f in P.folders(db)}
    rows, seen = [], set()

    def added(f, warn=""):
        ppl = len(P.folder_people(db, f["id"]))
        chats = db.scalar("SELECT COUNT(*) FROM chats WHERE folder_id=?", (f["id"],))
        leads = folder_leads(ctx, f["id"])["total"]
        mark = "" if f["delay_on"] else " ⛔"
        return [(f"{warn or '✅'} {f['name']} · 👤{ppl} · 💬{chats} · 🔥{leads}{mark}", f"cfo:{f['id']}")]

    for t in tg:
        k = folder_key(t)
        if k in seen:
            continue
        seen.add(k)
        f = mine.get(k)
        rows.append(added(f) if f else [(f"➕ {t}", f"cft:{_fkey_hash(t)}")])
    for k, f in mine.items():
        if k not in seen:
            rows.append(added(f, "⚠️"))
    note = [r.L("Asosiy akkauntdagi papkalar. <b>➕</b> — qo'shish (chatlari o'zi keladi). <b>✅</b> — ochish: "
                "xodimlar, nazorat, o'chirish.",
                "Папки основного аккаунта. <b>➕</b> — добавить (чаты подтянутся сами). <b>✅</b> — открыть: "
                "сотрудники, контроль, удаление."),
            r.L("👤 javob beradigan xodimlar · 💬 guruhlar · 🔥 lidlar (hammasi)",
                "👤 отвечающие сотрудники · 💬 группы · 🔥 лиды (все)")]
    if not online:
        note.append(r.L("⚠️ Asosiy akkaunt ulanmagan — Telegram papkalari ko'rinmaydi (⚙️ → 🔑 Asosiy akkaunt).",
                        "⚠️ Основной аккаунт не подключён — папки Telegram не видны (⚙️ → 🔑 Основной аккаунт)."))
    elif not tg:
        note.append(r.L("Asosiy akkauntda papka yo'q.", "У основного аккаунта нет папок."))
    if any(k not in seen for k in mine):
        note.append(r.L("⚠️ — Telegram'da bunday papka yo'q (nomini to'g'rilang yoki o'chiring).",
                        "⚠️ — такой папки нет в Telegram (переименуйте или удалите)."))
    rows += [[(r.L("🔄 Yangilash", "🔄 Обновить"), "cfs"), (r.L("✍️ Nom bilan", "✍️ По названию"), "cfa")],
             nav(r, "c")]
    return ui.join(title("📁", r.L("PAPKALAR", "ПАПКИ")), "", card(note)), kb(*rows)


@screen("cft", "full")
async def folder_take(ctx, r: Req):
    """➕ Telegram papkasini qo'shish — nomi aynan Telegram'dagidek, chatlari darhol tortiladi."""
    import asyncio
    want = r.args[0] if r.args else ""
    t = next((x for x in await _tg_folders(ctx) if _fkey_hash(x) == want), None)
    ui.view(r, "cf")
    if t is None:
        return await folders(ctx, r)
    fid = P.add_folder(ctx.db, t)
    if fid is not None and ctx.userbot is not None and ctx.userbot.state == "online":
        try:
            await asyncio.wait_for(ctx.userbot.sync_folders(), 15)
        except Exception:
            ui.bg(ctx.userbot.sync_all())
    return await folders(ctx, r)


@screen("cfs", "full")
async def folders_sync(ctx, r: Req):
    if ctx.userbot is None or ctx.userbot.state != "online":
        return r.L("⚠️ Asosiy akkaunt ulanmagan", "⚠️ Основной аккаунт не подключён")
    ui.bg(ctx.userbot.sync_all())
    await ui.toast(ctx.bot, r.chat_id, r.L("🔄 Yangilanmoqda…", "🔄 Обновляю…"))
    return await folders(ctx, r)


@screen("cfa", "full")
async def folder_add_ask(ctx, r: Req):
    ui.ask(r, "folder_add", "cf")
    return title("📁", r.L("YANGI PAPKA", "НОВАЯ ПАПКА")) + "\n\n" + card(
        [r.L("Papka nomini yuboring (Telegram'dagidek), masalan <code>RD 7</code>.",
             "Пришлите название папки (как в Telegram), например <code>RD 7</code>.")]), ui.cancel_kb(r, "cf")


@on_input("folder_add")
async def folder_add(ctx, r: Req):
    fid = P.add_folder(ctx.db, r.text)
    if fid is None:
        return r.L("⚠️ Bunday papka bor yoki nom bo'sh", "⚠️ Такая папка уже есть или пустое имя")
    if ctx.userbot is not None and ctx.userbot.state == "online":
        ui.bg(ctx.userbot.sync_all())
    r.args = [str(fid)]
    return await folder_card(ctx, r)


@screen("cfo", "full")
async def folder_card(ctx, r: Req):
    db = ctx.db
    fid = int(r.args[0])
    f = P.folder(db, fid)
    if f is None:
        return await folders(ctx, r)
    ppl = P.folder_people(db, fid)
    chats = db.scalar("SELECT COUNT(*) FROM chats WHERE folder_id=?", (fid,))
    lc = folder_leads(ctx, fid)
    from .panel_push import dstr
    base_d = dstr(db.get("push_base_from") or "2026-08-28")[:5]
    lines = [f"👤 {r.L('Xodimlar', 'Сотрудники')} — " + (h(", ".join(P.mention(p) for p in ppl)) or
                                                         r.L("belgilanmagan ⚠️", "не назначены ⚠️")),
             f"💬 {r.L('Guruhlar', 'Группы')} — <b>{chats}</b>",
             f"🔥 {r.L('Lidlar', 'Лиды')} — <b>{lc['total']}</b> {r.L('ta', '')}".rstrip()
             + f" · 🆕 {r.L('bugun yangi', 'новых сегодня')} <b>{lc['new']}</b>",
             f"└ {r.L(f'Push bazasi ({base_d} dan keyin o‘zi yozgan)', f'База Пуш (писали сами после {base_d})')} — "
             f"<b>{lc['all']}</b> · {r.L('7 kunda yozgan', 'писали за 7 дней')} <b>{lc['week']}</b> · "
             f"{r.L('bugun', 'сегодня')} <b>{lc['today']}</b>",
             f"🚨 {r.L('Zaderjka nazorati', 'Контроль задержек')} — {onoff(r, f['delay_on'])}",
             today_line(ctx, r, fid)]
    rows = grid([(f"👤 {r.L('Xodimlar', 'Сотрудники')}", f"cfp:{fid}"), (f"💬 {r.L('Guruhlar', 'Группы')}", f"cfc:{fid}"),
                 (f"📅 {r.L('Bugun kim', 'Кто сегодня')}", f"rtf:{fid}"),
                 ((r.L("⛔ Nazoratni o'chirish", "⛔ Выкл. контроль") if f["delay_on"] else r.L("✅ Nazoratni yoqish",
                                                                                       "✅ Вкл. контроль")),
                  f"cfd:{fid}"),
                 (f"✏️ {r.L('Nomi', 'Название')}", f"cfr:{fid}"), (f"🗑 {r.L('O‘chirish', 'Удалить')}", f"cfx:{fid}")])
    rows.append([(r.L("🔄 Telegram'dan yangilash", "🔄 Обновить из Telegram"), "cfs")])
    rows.append(nav(r, "cf"))
    return ui.join(title("📁", h(f["name"])), "", card(lines),
                   r.L("<i>💬 — papkadagi guruhlar, har guruhda lidlar — topiklar. 🔥 — hamma lidlar; "
                       "Push faqat baza sanasidan keyin o'zi yozganlarga boradi (yangi ham, eski ham).</i>",
                       "<i>💬 — группы папки, лиды — топики в них. 🔥 — все лиды; Пуш идёт только тем, "
                       "кто писал сам после даты базы (новые и старые).</i>")), kb(*rows)


@screen("cfd", "full")
async def folder_delay(ctx, r: Req):
    f = must(P.folder(ctx.db, int(r.args[0])))
    P.set_folder(ctx.db, f["id"], delay_on=0 if f["delay_on"] else 1)
    return await folder_card(ctx, r)


@screen("cfp", "full")
async def folder_people(ctx, r: Req):
    db = ctx.db
    fid = int(r.args[0])
    if len(r.args) > 1:
        P.toggle_folder_person(db, fid, int(r.args[1]))
    f = must(P.folder(db, fid))
    members = {p["id"] for p in P.folder_people(db, fid)}
    rows = []
    for p in P.people(db):
        mark = "✅" if p["id"] in members else "▫️"
        rows.append((f"{mark} {p['name']}", f"cfp:{fid}:{p['id']}"))
    rows = grid(rows)
    rows.append([(r.L("➕ Yangi xodim", "➕ Новый сотрудник"), f"pn:{fid}")])
    rows.append(nav(r, f"cfo:{fid}"))
    return ui.join(title("👤", h(f["name"]), r.L("kim belgilanadi va jarima oladi", "кого отмечать и штрафовать")),
                   "", card([r.L("Bosing — qo'shish / olib tashlash.", "Нажмите — добавить / убрать.")])), kb(*rows)


@screen("cfc", "full")
async def folder_chats(ctx, r: Req):
    db = ctx.db
    fid = int(r.args[0])
    if len(r.args) > 2 and r.args[1] == "x":
        db.run("DELETE FROM chats WHERE chat_id=? AND folder_id=?", (int(r.args[2]), fid))
        ctx.tracker.reload()
    f = must(P.folder(db, fid))
    chats = P.chats(db, fid)
    lines = [f"• {h(c['title'] or c['chat_id'])}" + (" 🧵" if c["is_forum"] else "") for c in chats[:30]]
    rows = [[(f"✖️ {c['title'][:28] or c['chat_id']}", f"cfc:{fid}:x:{c['chat_id']}")] for c in chats
            if c["source"] == "manual"][:10]
    rows.append([(r.L("➕ ID bo'yicha chat", "➕ Чат по ID"), f"cfca:{fid}")])
    rows.append(nav(r, f"cfo:{fid}"))
    body = card(lines) if lines else r.L("<i>Chat yo'q. Telegram'da shu nomli papka borligini tekshiring.</i>",
                                         "<i>Чатов нет. Проверьте папку с таким названием в Telegram.</i>")
    return ui.join(title("💬", h(f["name"]), f"{len(chats)}"), "", body), kb(*rows)


@screen("cfca", "full")
async def folder_chat_add_ask(ctx, r: Req):
    fid = int(r.args[0])
    ui.ask(r, "folder_chat", f"cfc:{fid}", fid=fid)
    return title("💬", r.L("CHAT QO'SHISH", "ДОБАВИТЬ ЧАТ")) + "\n\n" + card(
        [r.L("Chat ID sini yuboring (masalan <code>-1001234567890</code>). ID ni bilish: chatdan xabarni menga "
             "yuboring yoki Sozlamalar → 🔎 Chat qidirish.",
             "Пришлите ID чата (например <code>-1001234567890</code>). Узнать ID: перешлите мне сообщение "
             "или Настройки → 🔎 Поиск чата.")]), ui.cancel_kb(r, f"cfc:{fid}")


@on_input("folder_chat")
async def folder_chat_add(ctx, r: Req, fid: int):
    import re
    ids = [int(x) for x in re.findall(r"-?\d{6,}", r.text)]
    if not ids:
        return r.L("⚠️ Chat ID si — son", "⚠️ ID чата — число")
    for cid in ids:
        ctx.db.run("INSERT INTO chats(chat_id, folder_id, source) VALUES(?,?, 'manual') ON CONFLICT(chat_id) DO UPDATE "
                   "SET folder_id=excluded.folder_id, source='manual'", (cid, fid))
    ctx.tracker.reload()
    r.args = [str(fid)]
    return await folder_chats(ctx, r)


@screen("cfr", "full")
async def folder_rename_ask(ctx, r: Req):
    fid = int(r.args[0])
    ui.ask(r, "folder_rename", f"cfo:{fid}", fid=fid)
    return title("✏️", r.L("PAPKA NOMI", "НАЗВАНИЕ ПАПКИ")) + "\n\n" + card(
        [r.L("Yangi nomni yuboring.", "Пришлите новое название.")]), ui.cancel_kb(r, f"cfo:{fid}")


@on_input("folder_rename")
async def folder_rename(ctx, r: Req, fid: int):
    if not P.rename_folder(ctx.db, fid, r.text):
        return r.L("⚠️ Bunday nom bor yoki bo'sh", "⚠️ Такое имя уже есть или пустое")
    r.args = [str(fid)]
    return await folder_card(ctx, r)


@screen("cfx", "full")
async def folder_delete_ask(ctx, r: Req):
    fid = int(r.args[0])
    f = must(P.folder(ctx.db, fid))
    return title("🗑", h(f["name"])) + "\n\n" + card(
        [r.L("Papka o'chirilsinmi? Xodimlar o'chmaydi, faqat papkadan chiqadi; chatlar nazoratdan chiqadi.",
             "Удалить папку? Сотрудники останутся, чаты уйдут из контроля.")]), \
        kb([(r.L("✅ Ha, o'chirish", "✅ Да, удалить"), f"cfxy:{fid}"), (r.L("✖️ Yo'q", "✖️ Нет"), f"cfo:{fid}")])


@screen("cfxy", "full")
async def folder_delete(ctx, r: Req):
    P.delete_folder(ctx.db, int(r.args[0]))
    ctx.tracker.reload()
    return await folders(ctx, r)
