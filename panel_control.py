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
          "echo": "xodimdan keyin darhol bot xabari — mijoz emas", "night": "ish vaqtidan tashqari — hisoblanmaydi"}
DEC_RU = {"dup": "повтор", "service": "служебное", "ours": "наш Пуш", "excluded": "⚡/💊 — не учитывается",
          "before": "до начала контроля", "stavka_skip": "идёт ставка — не учитывается", "stavka_bet": "кружок ставки",
          "bet_text": "текст ставки", "stavka_end": "ставка закончилась", "auto_bet": "автоставка",
          "wait": "клиент ждёт ответа", "wait_more": "клиент дописал",
          "wait_last": "клиент дописал подряд — считаем с этого сообщения", "reply": "сотрудник ответил ✅",
          "staff": "сотрудник написал", "alert": "«задержка» отправлена",
          "echo": "сразу после сотрудника сообщение бота — не клиент", "night": "вне рабочего времени — не считается"}
WHO_UZ = {"client": "mijoz (bot)", "staff": "xodim", "ours": "Push", "service": "xizmat", "": ""}
WHO_RU = {"client": "клиент (бот)", "staff": "сотрудник", "ours": "Пуш", "service": "служебное", "": ""}


def work_hours(ctx) -> str:
    return f"{ctx.db.get('work_start')}–{ctx.db.get('work_end')}"


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
             clean_line(ctx, r),
             remind_line(ctx, r),
             f"🔒 {r.L('Qattiq rejim', 'Строгий режим')} — {onoff(r, db.flag('strict_on'))}",
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
        rows.append([(f"💸 {r.L('Jarima qoidasi', 'Правила штрафа')}", "cfn"),
                     (f"📌 {r.L('Doska', 'Доска')}", "cpb")])
        rows.append([(f"🧹 {r.L('«Проёб»ni tozalash', 'Очистка «Проёб»')}", "ccl"),
                     (f"🔒 {r.L('Qattiq rejim', 'Строгий режим')}", "cst")])
        rows.append([(f"⏰ {r.L('Javobsiz zaderjka', 'Задержка без ответа')}", "crm")])
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
             r.L(f"📣 Boshqa xabarlar (soviyotgan lidlar, kechikish, Push tugadi, jarima ogohlantirishi, stavka) — "
                 f"yozilganidan keyin: <b>{_mins(r, i)}</b>",
                 f"📣 Остальное («остывают», «Опоздание», «Пуш завершён», предупреждения, «ставка») — после отправки: "
                 f"<b>{_mins(r, i)}</b>"),
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


REMIND_CHOICES = (10, 15, 20, 30, 45, 60)
GRACE_CHOICES = (3, 5, 10, 15, 20, 30)


def remind_line(ctx, r: Req) -> str:
    on, after, grace, usd = ctx.tracker.alert_remind_rules()
    if not on:
        return f"⏰ {r.L('Javobsiz zaderjka', 'Задержка без ответа')} — {onoff(r, False)}"
    return (f"⏰ {r.L('Javobsiz zaderjka', 'Задержка без ответа')} — "
            + r.L(f"{after // 60} daq → eslatma → {grace // 60} daq → <b>{usd:g} $</b>",
                  f"{after // 60} мин → напоминание → {grace // 60} мин → <b>{usd:g} $</b>"))


@screen("crm", "full")
async def remind_screen(ctx, r: Req):
    """⏰ Zaderjka javobsiz qolsa: N daqiqada eslatma (o'sha xabarga javob qilib), muhlatda javob yo'q — jarima."""
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
    on, after, grace, usd = ctx.tracker.alert_remind_rules()
    lines = [f"{r.L('Holat', 'Состояние')}: " + (r.L("🟢 <b>yoqiq</b>", "🟢 <b>включено</b>") if on else
                                                 r.L("⚪ o'chiq", "⚪ выключено")),
             r.L(f"1) Zaderjka xabari chiqqanidan <b>{after // 60} daqiqa</b> o'tib ham javob bo'lmasa — eslatma: o'sha "
                 "xabarga javob qilib, xodimlar belgilanadi. Ish kuni tugaganda hali javobsiz bo'lsa — darhol.",
                 f"1) Если через <b>{after // 60} мин</b> после «задержки» ответа нет — напоминание ответом на это "
                 "сообщение, с отметкой сотрудников. Если рабочий день закончился, а ответа нет — сразу."),
             r.L(f"2) Eslatmadan keyin <b>{grace // 60} daqiqa</b>da javob bo'lmasa — jarima <b>{usd:g} $</b> o'sha kuni "
                 "papkada ishlayotgan har xodimga. Jarima xabari «Проёб»da qoladi.",
                 f"2) Если через <b>{grace // 60} мин</b> после напоминания ответа нет — штраф <b>{usd:g} $</b> каждому "
                 "сотруднику папки, который сегодня на работе. Сообщение о штрафе остаётся в «Проёб»."),
             r.L("<i>«Holat» (ko'p lid javobsiz) uchun jarima olgan havolalar bu yerda qayta jarimaga kirmaydi.</i>",
                 "<i>Ссылки, за которые уже был штраф по «много лидов без ответа», повторно не штрафуются.</i>")]
    d = r.L("daq", "мин")
    row_r = [(("✅ " if after // 60 == v else "") + f"⏰ {v} {d}", f"crm:r:{v}") for v in REMIND_CHOICES]
    row_g = [(("✅ " if grace // 60 == v else "") + f"⏳ {v} {d}", f"crm:g:{v}") for v in GRACE_CHOICES]
    rows = grid(row_r, 3) + grid(row_g, 3)
    rows.append([(f"💸 {r.L('Jarima', 'Штраф')}: {usd:g} $", "crmf"),
                 ((r.L("⛔ O'chirish", "⛔ Выключить"), "crm:off") if on else (r.L("✅ Yoqish", "✅ Включить"), "crm:on"))])
    rows.append(nav(r, "c"))
    return ui.join(title("⏰", r.L("JAVOBSIZ ZADERJKA", "ЗАДЕРЖКА БЕЗ ОТВЕТА")), "", card(lines),
                   r.L("<i>⏰ — eslatma qachon · ⏳ — eslatmadan keyin muhlat</i>",
                       "<i>⏰ — когда напомнить · ⏳ — срок после напоминания</i>")), kb(*rows)


@screen("crmf", "full")
async def remind_fine_ask(ctx, r: Req):
    ui.ask(r, "remind_fine", "crm")
    return (title("💸", r.L("ESLATMADAN KEYIN JARIMA", "ШТРАФ ПОСЛЕ НАПОМИНАНИЯ")) + "\n\n" +
            card([r.L(f"Hozir: <b>{ctx.db.get('remind_fine_usd')} $</b> har xodimga.",
                      f"Сейчас: <b>{ctx.db.get('remind_fine_usd')} $</b> каждому."),
                  r.L("Necha $ bo'lsin? Son yuboring (0 — jarimasiz, faqat eslatma).",
                      "Сколько $? Пришлите число (0 — без штрафа, только напоминание).")]),
            ui.cancel_kb(r, "crm"))


@on_input("remind_fine")
async def set_remind_fine(ctx, r: Req):
    v = parse_number(r.text)
    if v is None or not 0 <= v <= 1000:
        return r.L("⚠️ 0 dan 1000 gacha son yuboring", "⚠️ Пришлите число от 0 до 1000")
    ctx.db.set("remind_fine_usd", f"{v:g}")
    r.args = []
    ui.view(r, "crm")
    return await remind_screen(ctx, r)


@screen("cst", "full")
async def strict_screen(ctx, r: Req):
    """🔒 Qattiq rejim (reglament jarimalari): nima qiladi — oddiy so'z bilan; yoqish / o'chirish."""
    db = ctx.db
    if r.args and r.args[0] in ("on", "off"):
        db.set("strict_on", "1" if r.args[0] == "on" else "0")
        ui.view(r, "cst")
    on = db.flag("strict_on")
    limit = db.get_int("limit_minutes", 20)
    lines = [f"{r.L('Holat', 'Состояние')}: " + (r.L("🟢 <b>yoqiq</b>", "🟢 <b>включён</b>") if on else
                                                 r.L("⚪ o'chiq", "⚪ выключен")),
             r.L("Jarima = hujjatdagi $ × xodim foizi (masalan, $15 × 41% = $6.15).",
                 "Штраф = $ из регламента × процент сотрудника (например, $15 × 41% = $6.15)."),
             "",
             r.L("<b>🕘 Kechikish</b> (o'sha kungi zp dan)", "<b>🕘 Опоздание</b> (от дневной ЗП)"),
             r.L("15 daqiqagacha — ogohlantirish · 15–30 — 15% · 30–60 — 30% · 60+ — 50%",
                 "до 15 мин — предупреждение · 15–30 — 15% · 30–60 — 30% · 60+ — 50%"),
             r.L("Haftada 3-kechikishdan boshlab — yana 10%. Summa kechki hisobotdan keyin aniqlanadi.",
                 "С 3-го опоздания за неделю — ещё 10%. Сумма — после вечернего отчёта."),
             "",
             r.L(f"<b>🐢 Sekin javob</b> ({limit}+ daqiqa), har hafta yangidan",
                 f"<b>🐢 Долгий ответ</b> ({limit}+ мин), каждую неделю заново"),
             r.L("1-marta — ogohlantirish · 2-marta — $15 × % · 3-dan boshlab har biri — $25 × %",
                 "1-й раз — предупреждение · 2-й — $15 × % · с 3-го каждый — $25 × %"),
             r.L("Kimga: o'sha kuni o'sha papkada ishlayotgan xodimlarga.",
                 "Кому: сотрудникам этой папки, которые сегодня на работе."),
             "",
             r.L("<b>🚪 Papkani tashlab ketish</b>", "<b>🚪 Уход с папки</b>"),
             r.L("Lid kutib turibdi, xodim tanaffus demasdan yo'q: 15+ daqiqa — $15 × % · 60+ daqiqa — jami $40 × %. "
                 "O'sha paytdagi sekin javoblar alohida jarima bo'lmaydi.",
                 "Лид ждёт, сотрудник отсутствует без объявленного перерыва: 15+ мин — $15 × % · 60+ мин — всего "
                 "$40 × %. Долгие ответы за это время отдельно не штрафуются."),
             "",
             r.L("Yoqilganda papka jarimasi va kechikishga daqiqasiga jarima ishlamaydi. Jarima xabarlari «Проёб»da "
                 "qoladi. Avtomat jarimalar o'chiq bo'lsa — qattiq rejim ham ishlamaydi.",
                 "Когда включён — штраф папки и поминутный штраф за опоздание не работают. Сообщения о штрафах "
                 "остаются в «Проёб». Если автоштрафы выключены — строгий режим тоже не работает.")]
    btn = [(r.L("⛔ O'chirish", "⛔ Выключить"), "cst:off")] if on else [(r.L("✅ Yoqish", "✅ Включить"), "cst:on")]
    return ui.join(title("🔒", r.L("QATTIQ REJIM", "СТРОГИЙ РЕЖИМ")), "", card(lines)), kb(btn, nav(r, "c"))


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


def fine_line(ctx, r: Req) -> str:
    db = ctx.db
    if not db.flag("fines_enabled"):
        return f"💸 {r.L('Avto-jarima', 'Авто-штрафы')} — {onoff(r, False)}"
    from .kassa_view import money
    n, forgive, grace = ctx.tracker.fine_rules()
    amt = money(db.get_float("fine_amount"))
    return (f"💸 {r.L('Avto-jarima', 'Авто-штрафы')} — {onoff(r, True)} · "
            + r.L(f"{n}+ lid · {grace // 60} daq · {amt} $ · {forgive} kechirim",
                  f"{n}+ лида · {grace // 60} мин · {amt} $ · {forgive} прощ."))


def folder_fine_text(ctx, r: Req, f) -> str:
    from .kassa_view import money
    own = float(f["fine_usd"] or 0)
    if own < 0:
        return r.L("jarimasiz", "без штрафа")
    if own > 0:
        return f"<b>{money(own)} $</b> " + r.L("(shu papka uchun)", "(для этой папки)")
    return f"<b>{money(ctx.db.get_float('fine_amount'))} $</b> " + r.L("(umumiy)", "(общая)")


@screen("cfn", "view")
async def fine_rules(ctx, r: Req):
    db = ctx.db
    if r.args and r.args[0] == "t" and r.can("full"):
        db.toggle("fines_enabled")
    from .attendance import late_fine_text
    from .kassa_view import money
    n, forgive, grace = ctx.tracker.fine_rules()
    on = db.flag("fines_enabled")
    ep = db.get_int("fine_episode", 30)
    amount = money(db.get_float("fine_amount"))
    late = h(late_fine_text(db.get("late_fine"), r.lang))
    from .rules import plural_leads
    raz = "раза" if forgive % 10 in (2, 3, 4) and forgive % 100 not in (12, 13, 14) else "раз"
    head = f"💸 {r.L('Avtomat jarimalar', 'Автоматические штрафы')} — {onoff(r, on)}"
    story = [f"<b>🚨 {r.L('Zaderjka uchun — qanday ishlaydi', 'За задержки — как работает')}</b>",
             r.L(f"1) Papkada bir vaqtda <b>{n} ta lid</b> javobsiz qolsa — bu «holat».",
                 f"1) В папке одновременно <b>{plural_leads(n)}</b> без ответа — это «случай»."),
             r.L(f"2) Kuniga birinchi <b>{forgive} marta</b> — faqat ogohlantirish, jarimasiz.",
                 f"2) Первые <b>{forgive} {raz}</b> в день — только предупреждение, без штрафа."),
             r.L(f"3) Keyingisida: «<b>{grace // 60} daqiqada</b> javob bering». Javob bo'lmasa — papkaning har "
                 f"xodimiga <b>{amount} $</b> (dam olayotganga emas).",
                 f"3) Дальше: «ответьте за <b>{grace // 60} мин</b>». Нет ответа — каждому сотруднику папки "
                 f"<b>{amount} $</b> (кроме выходных)."),
             r.L(f"4) Jarimadan keyin <b>{ep} daqiqa</b> ichidagi kechikishlar — o'sha holat, ikkinchi jarima yo'q.",
                 f"4) Задержки в течение <b>{ep} мин</b> после штрафа — тот же случай, второго штрафа нет.")]
    other = [f"<b>🕘 {r.L('Kech qolish', 'Опоздание')}</b> — {late}"]
    folders = P.folders(db)
    if folders:
        other.append(f"<b>📁 {r.L('Papkalar', 'Папки')}</b>")
        other += [f"{h(f['name'])} — {folder_fine_text(ctx, r, f)}" for f in folders]
    rows = []
    if r.can("full"):
        d = r.L("daq", "мин")
        rows += grid([(f"👥 {r.L(f'{n} ta lid', plural_leads(n))}", "cfi:fine_min_leads"),
                      (f"🙏 {r.L(f'{forgive} marta kechirish', f'прощать {forgive} {raz}')}", "cfi:fine_forgive"),
                      (f"⏳ {grace // 60} {d}", "cfi:fine_grace"),
                      (f"💵 {amount} $", "cfi:fine_amount"),
                      (f"🔁 {ep} {d}", "cfi:fine_episode"),
                      (f"🕘 {r.L('Kech qolish', 'Опоздание')}", "cfi:late_fine")])
        rows.append([(f"📁 {r.L('Papka bo‘yicha summa', 'Сумма по папкам')}", "cf")])
        rows.append([((r.L("⛔ Jarimalarni o'chirish", "⛔ Выключить штрафы") if on else
                       r.L("✅ Jarimalarni yoqish", "✅ Включить штрафы")), "cfn:t")])
    rows.append(nav(r, "c"))
    hint = r.L("O'zgartirish: pastdagi raqamni bosing va yangisini yozing.",
               "Изменить: нажмите на число внизу и напишите новое.")
    return ui.join(title("💸", r.L("JARIMALAR", "ШТРАФЫ")), "", head, card(story), card(other), f"<i>{hint}</i>"), \
        kb(*rows)


FINE_KEYS = {"fine_min_leads": (1, 50), "fine_forgive": (0, 20), "fine_grace": (0, 120), "fine_amount": (0, 1000),
             "fine_episode": (0, 600), "late_fine": None}


@screen("cfi", "full")
async def fine_rule_ask(ctx, r: Req):
    key = r.args[0] if r.args else ""
    if key not in FINE_KEYS:
        r.args = []
        return await fine_rules(ctx, r)
    ui.ask(r, "fine_rule", "cfn", key=key)
    prompts = {"fine_min_leads": r.L("Bitta papkada nechta lid BIRDANIGA javobsiz qolsa jarima holati bo'lsin? "
                                     "(masalan <code>3</code>)",
                                     "Сколько лидов СРАЗУ без ответа в одной папке — случай для штрафа? "
                                     "(например <code>3</code>)"),
               "fine_grace": r.L("Ogohlantirishdan keyin javob uchun necha daqiqa? (masalan <code>3</code>)",
                                 "Сколько минут на ответ после предупреждения? (например <code>3</code>)"),
               "fine_amount": r.L("Jarima summasi ($), papkaning har xodimiga. Masalan <code>5</code>. "
                                  "<code>0</code> — jarimasiz.",
                                  "Сумма штрафа ($) каждому сотруднику папки. Например <code>5</code>. "
                                  "<code>0</code> — без штрафа."),
               "fine_forgive": r.L("Har kuni har papkaga necha marta kechirilsin? (<code>0</code> — kechirilmaydi)",
                                   "Сколько раз в день прощать каждой папке? (<code>0</code> — не прощать)"),
               "fine_episode": r.L("Jarimadan keyin necha daqiqa ichidagi yangi kechikishlar o'sha holat hisoblansin "
                                   "(qayta jarima yo'q)? Masalan <code>30</code>.",
                                   "Сколько минут после штрафа новые задержки считать тем же случаем (без нового "
                                   "штрафа)? Например <code>30</code>."),
               "late_fine": r.L("Kech qolish jarimasi:\n• <code>0.5</code> — har daqiqaga 0.5 $;\n"
                                "• <code>10=2, 30=5</code> — 10+ daqiqa → 2 $, 30+ daqiqa → 5 $;\n"
                                "• <code>0</code> — jarimasiz.",
                                "Штраф за опоздание:\n• <code>0.5</code> — 0.5 $ за минуту;\n"
                                "• <code>10=2, 30=5</code> — 10+ мин → 2 $, 30+ мин → 5 $;\n"
                                "• <code>0</code> — без штрафа.")}
    cur = ctx.db.get(key) or "0"
    return title("💸", r.L("JARIMA QOIDASI", "ПРАВИЛА ШТРАФА")) + "\n\n" + card(
        [r.L(f"Hozir: <code>{h(cur)}</code>", f"Сейчас: <code>{h(cur)}</code>"), prompts[key]]), \
        ui.cancel_kb(r, "cfn")


@on_input("fine_rule")
async def fine_rule_set(ctx, r: Req, key: str):
    if key == "late_fine":
        from .attendance import parse_late_fine
        try:
            rule = parse_late_fine(r.text)
        except ValueError:
            return r.L("⚠️ Masalan: 0.5 yoki 10=2, 30=5", "⚠️ Например: 0.5 или 10=2, 30=5")
        if rule is None:
            ctx.db.set(key, "")
        elif rule[0] == "rate":
            ctx.db.set(key, f"{rule[1]:g}")
        else:
            ctx.db.set(key, ", ".join(f"{m}={usd:g}" for m, usd in rule[1]))
        r.args = []
        return await fine_rules(ctx, r)
    v = parse_number(r.text)
    lo, hi = FINE_KEYS[key]
    whole = key != "fine_amount"
    if v is None or not lo <= v <= hi or (whole and v != int(v)):
        return r.L(f"⚠️ {lo} dan {hi} gacha son", f"⚠️ Число от {lo} до {hi}")
    ctx.db.set(key, str(int(v)) if whole else f"{v:g}")
    r.args = []
    return await fine_rules(ctx, r)


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
    need, _next, cap, _window = ctx.tracker.stavka_limits()
    first, nxt, max_n = ctx.tracker.remind_rules()
    running = db.scalar("SELECT COUNT(*) FROM threads WHERE stavka='on'")
    d = r.L("daq", "мин")
    text = ui.join(
        title("🎬", r.L("STAVKA (YANGI LID)", "СТАВКА (НОВЫЙ ЛИД)")), "",
        card([f"{r.L('Holat', 'Состояние')} — {onoff(r, db.flag('stavka_enabled'))}",
              f"🎬 {r.L('Tugashi', 'Завершение')} — <b>{need}</b> {r.L('ta stavka (dumaloq video)', 'ставки (кружка)')}",
              f"⏱ {r.L('1-stavka kutiladi', 'Первая ставка ждём')} — <b>{first // 60} {d}</b>",
              f"⏱ {r.L('Keyingilari', 'Следующие')} — <b>{nxt // 60} {d}</b> {r.L('oldingisidan', 'после предыдущей')}",
              f"🔔 {r.L('Eslatma', 'Напоминаний')} — <b>{max_n}</b> {r.L('martagacha', 'максимум')}",
              f"🛟 {r.L('Eng uzoq', 'Максимум')} — <b>{cap // 60} {d}</b>",
              f"{r.L('Hozir stavkada', 'Сейчас в ставке')} — <b>{running}</b>"]),
        card([r.L(f"Yangi chat → stavka. Stavka = dumaloq video (vositachi bot tashlaydi; tushmasa xodim o'zi "
                  f"yuboradi — u ham sanaladi). {first // 60} daqiqada birinchisi, keyin har {nxt // 60} daqiqada "
                  f"keyingisi kelmasa «ставка» eslatiladi (ko'pi bilan {max_n} marta). {need} ta stavkadan keyin "
                  "oddiy nazorat. Stavka paytida xabarlar zaderjka hisoblanmaydi.",
                  f"Новый чат → ставка. Ставка = кружок (ставит бот-посредник; если нет — сотрудник сам, это тоже "
                  f"считается). Нет первой за {first // 60} мин или следующей за {nxt // 60} мин — напоминание "
                  f"«ставка» (не больше {max_n} раз). После {need} ставок — обычный контроль. Во время ставки "
                  "сообщения не считаются задержкой.")]))
    rows = [[((r.L("⛔ O'chirish", "⛔ Выключить") if db.flag("stavka_enabled") else r.L("✅ Yoqish", "✅ Включить")),
              "cst")],
            [(r.L("✏️ Sonlarni o'zgartirish", "✏️ Изменить числа"), "csn")], nav(r, "c")]
    return text, kb(*rows)


@screen("cst", "full")
async def stavka_toggle(ctx, r: Req):
    ctx.db.toggle("stavka_enabled")
    return await stavka(ctx, r)


STAVKA_KEYS = (("stavka_count", 1, 20), ("stavka_first", 1, 180), ("stavka_next", 1, 180),
               ("stavka_max_remind", 0, 10), ("stavka_cap", 10, 1440))


@screen("csn", "full")
async def stavka_ask(ctx, r: Req):
    ui.ask(r, "stavka", "cs")
    now = " ".join(ctx.db.get(k) for k, _lo, _hi in STAVKA_KEYS)
    return (title("🎬", r.L("STAVKA SONLARI", "ЧИСЛА СТАВКИ")) + "\n\n" +
            card([r.L(f"Hozir: <code>{now}</code>", f"Сейчас: <code>{now}</code>"),
                  r.L("5 ta son yuboring, masalan <code>3 20 20 3 180</code>:\n1) nechta stavka;\n"
                      "2) birinchisi necha daqiqada kelishi kerak;\n3) keyingisi oldingisidan necha daqiqada;\n"
                      "4) eslatma ko'pi bilan necha marta;\n5) stavka eng uzoq necha daqiqa.",
                      "Пришлите 5 чисел, например <code>3 20 20 3 180</code>:\n1) сколько ставок;\n"
                      "2) за сколько минут первая;\n3) следующая после предыдущей — минут;\n"
                      "4) напоминаний максимум;\n5) ставка максимум минут.")]),
            ui.cancel_kb(r, "cs"))


@on_input("stavka")
async def stavka_set(ctx, r: Req):
    import re
    nums = [int(x) for x in re.findall(r"\d+", r.text)]
    if not 1 <= len(nums) <= len(STAVKA_KEYS) or any(not lo <= v <= hi for v, (_k, lo, hi) in zip(nums, STAVKA_KEYS)):
        return r.L("⚠️ Masalan: 3 20 20 3 180", "⚠️ Например: 3 20 20 3 180")
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
             f"💸 {r.L('Jarima', 'Штраф')} — {folder_fine_text(ctx, r, f)}"
             + ("" if ctx.db.flag("fines_enabled") else r.L(" · ⚪ jarimalar o'chiq", " · ⚪ штрафы выключены"))]
    rows = grid([(f"👤 {r.L('Xodimlar', 'Сотрудники')}", f"cfp:{fid}"), (f"💬 {r.L('Guruhlar', 'Группы')}", f"cfc:{fid}"),
                 (f"💸 {r.L('Jarima', 'Штраф')}", f"cff:{fid}"),
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


@screen("cff", "full")
async def folder_fine_ask(ctx, r: Req):
    fid = int(r.args[0])
    ui.ask(r, "folder_fine", f"cfo:{fid}", fid=fid)
    from .kassa_view import money
    return title("💸", r.L("PAPKA JARIMASI", "ШТРАФ ПАПКИ")) + "\n\n" + card(
        [r.L(f"Umumiy summa: <b>{money(ctx.db.get_float('fine_amount'))} $</b> (💸 Jarima qoidasi).",
             f"Общая сумма: <b>{money(ctx.db.get_float('fine_amount'))} $</b> (💸 Правила штрафа)."),
         r.L("Shu papka uchun alohida summa yuboring, masalan <code>5</code>.\n<code>0</code> — umumiy summa.\n"
             "<code>-</code> — bu papkada jarima yo'q.",
             "Пришлите отдельную сумму для этой папки, например <code>5</code>.\n<code>0</code> — общая сумма.\n"
             "<code>-</code> — в этой папке без штрафа.")]), ui.cancel_kb(r, f"cfo:{fid}")


@on_input("folder_fine")
async def folder_fine(ctx, r: Req, fid: int):
    t = r.text.strip()
    if t in ("-", "—", "yo'q", "нет"):
        v = -1.0
    else:
        v = parse_number(t)
        if v is None or v < 0 or v > 1000:
            return r.L("⚠️ Son yuboring, masalan 5 (yoki 0, -)", "⚠️ Пришлите число, например 5 (или 0, -)")
    P.set_folder(ctx.db, fid, fine_usd=v)
    r.args = [str(fid)]
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
