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
          "reply": "xodim javob berdi ✅", "staff": "xodim yozdi", "alert": "«задержка» yuborildi",
          "echo": "xodimdan keyin darhol bot xabari — mijoz emas", "night": "ish vaqtidan tashqari — hisoblanmaydi"}
DEC_RU = {"dup": "повтор", "service": "служебное", "ours": "наш Push", "excluded": "⚡/💊 — не учитывается",
          "before": "до начала контроля", "stavka_skip": "идёт ставка — не учитывается", "stavka_bet": "кружок ставки",
          "bet_text": "текст ставки", "stavka_end": "ставка закончилась", "auto_bet": "автоставка",
          "wait": "клиент ждёт ответа", "wait_more": "клиент дописал", "reply": "сотрудник ответил ✅",
          "staff": "сотрудник написал", "alert": "«задержка» отправлена",
          "echo": "сразу после сотрудника сообщение бота — не клиент", "night": "вне рабочего времени — не считается"}
WHO_UZ = {"client": "mijoz (bot)", "staff": "xodim", "ours": "Push", "service": "xizmat", "": ""}
WHO_RU = {"client": "клиент (бот)", "staff": "сотрудник", "ours": "Push", "service": "служебное", "": ""}


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
             f"🕒 {r.L('Ish vaqti', 'Рабочее время')} — <b>{work_hours(ctx)}</b>",
             f"🎬 {r.L('Stavka', 'Ставка')} — {onoff(r, db.flag('stavka_enabled'))} · <b>{need}</b> "
             f"{r.L('video', 'кружка')}",
             f"⏳ {r.L('Hozir kutyapti', 'Сейчас ждут')} — <b>{waiting}</b>",
             fine_line(ctx, r)]
    if not group:
        lines.append(r.L("⚠️ «Проёб» guruhi belgilanmagan (Sozlamalar)", "⚠️ Группа «Проёб» не задана (Настройки)"))
    text = ui.join(title("🚨", r.L("NAZORAT", "КОНТРОЛЬ")), "", card(lines),
                   r.L("<i>Mijoz = vositachi bot xabari. Javob = har qanday xodim xabari (papka akkauntidan ham). "
                       "Push xabari va xodim yozgan zahoti chiqqan bot xabari hisobga olinmaydi.</i>",
                       "<i>Клиент = сообщение бота-посредника. Ответ = сообщение любого сотрудника (и с аккаунта "
                       "папки). Push и сообщение бота сразу после сотрудника не считаются.</i>"))
    rows = []
    if r.can("full"):
        rows += grid([(f"⏱ {r.L('Limit', 'Лимит')}", "cl"), (f"🕒 {r.L('Ish vaqti', 'Рабочее время')}", "ch"),
                      (f"🎬 {r.L('Stavka', 'Ставка')}", "cs"), (f"📁 {r.L('Papkalar', 'Папки')}", "cf")])
        rows.append([(f"💸 {r.L('Jarima qoidasi', 'Правила штрафа')}", "cfn")])
    rows += grid([(f"⏳ {r.L('Kutayotganlar', 'Ожидают')}", "cw"), (f"🔍 {r.L('Lidni tekshirish', 'Проверить лид')}", "cc")])
    if r.can("full"):
        rows.append([((r.L("⛔ Zaderjkani o'chirish", "⛔ Выключить контроль") if db.flag("delay_enabled")
                       else r.L("✅ Zaderjkani yoqish", "✅ Включить контроль")), "ct")])
        rows.append([(f"🧾 {r.L('Qarorlar jurnali (fayl)', 'Журнал решений (файл)')}", "cj")])
    rows.append(nav(r))
    return text, kb(*rows)


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
    d = r.L("daq", "мин")
    lines = [f"💸 {r.L('Avtomat jarimalar', 'Автоматические штрафы')} — {onoff(r, on)}", "",
             f"<b>🚨 {r.L('Zaderjka', 'Задержка')}</b>",
             f"👥 {r.L('Nechta lid birdaniga', 'Сколько лидов сразу')} — <b>{n}</b>",
             f"⏳ {r.L('Javob uchun vaqt', 'Время на ответ')} — <b>{grace // 60} {d}</b>",
             f"💵 {r.L('Summa', 'Сумма')} — <b>{money(db.get_float('fine_amount'))} $</b> "
             f"{r.L('har xodimga', 'каждому')}",
             f"🙏 {r.L('Kechirim', 'Прощать')} — <b>{forgive}</b> {r.L('marta har kuni', 'раз в день')}",
             f"🔁 {r.L('Bitta holat', 'Один случай')} — <b>{db.get_int('fine_episode', 30)} {d}</b>",
             "", f"<b>🕘 {r.L('Kech qolish', 'Опоздание')}</b> — {h(late_fine_text(db.get('late_fine'), r.lang))}"]
    folders = P.folders(db)
    if folders:
        lines.append("")
        lines += [f"📁 {h(f['name'])} — {folder_fine_text(ctx, r, f)}" for f in folders]
    how = [r.L(f"Papkada {n} ta lid birdaniga javobsiz qolsa — «Проёб»ga ogohlantirish. Kuniga birinchi {forgive} "
               f"tasi kechiriladi. Keyingisida «{grace // 60} daqiqada javob bering», javob bo'lmasa — summa papkaning "
               f"har xodimiga (dam olayotganga emas). {db.get_int('fine_episode', 30)} daqiqa ichida yana kechiksa — "
               "o'sha holat, qayta jarima yo'q.",
               f"{n} лидов сразу без ответа в папке — предупреждение в «Проёб». Первые {forgive} в день прощаются. "
               f"Дальше «ответьте за {grace // 60} мин», нет ответа — сумма каждому сотруднику папки (кроме "
               f"выходных). Повтор в течение {db.get_int('fine_episode', 30)} мин — тот же случай.")]
    rows = []
    if r.can("full"):
        rows.append([((r.L("⛔ Jarimalarni o'chirish", "⛔ Выключить штрафы") if on else
                       r.L("✅ Jarimalarni yoqish", "✅ Включить штрафы")), "cfn:t")])
        rows += grid([(f"👥 {r.L('Nechta lid', 'Сколько лидов')}", "cfi:fine_min_leads"),
                      (f"⏳ {r.L('Javob vaqti', 'Время на ответ')}", "cfi:fine_grace"),
                      (f"💵 {r.L('Summa', 'Сумма')}", "cfi:fine_amount"),
                      (f"🙏 {r.L('Kechirim', 'Прощать')}", "cfi:fine_forgive"),
                      (f"🔁 {r.L('Bitta holat', 'Один случай')}", "cfi:fine_episode"),
                      (f"🕘 {r.L('Kech qolish', 'Опоздание')}", "cfi:late_fine")])
        rows.append([(f"📁 {r.L('Papka bo‘yicha summa', 'Сумма по папкам')}", "cf")])
    rows.append(nav(r, "c"))
    return ui.join(title("💸", r.L("JARIMA QOIDASI", "ПРАВИЛА ШТРАФА")), "", card(lines), card(how)), kb(*rows)


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
@screen("cf", "full")
async def folders(ctx, r: Req):
    db = ctx.db
    rows = []
    for f in P.folders(db):
        ppl = len(P.folder_people(db, f["id"]))
        chats = db.scalar("SELECT COUNT(*) FROM chats WHERE folder_id=?", (f["id"],))
        mark = "" if f["delay_on"] else " ⛔"
        rows.append([(f"📁 {f['name']} · 👤{ppl} · 💬{chats}{mark}", f"cfo:{f['id']}")])
    missing = getattr(ctx.userbot, "missing_folders", []) if ctx.userbot else []
    note = [r.L("Papka nomi Telegram'dagi papka nomi bilan bir xil bo'lsin — chatlar o'zi qo'shiladi.",
                "Название папки = названию папки в Telegram — чаты подтянутся сами.")]
    if missing:
        note.append("⚠️ " + r.L("Telegram'da topilmadi: ", "Нет в Telegram: ") + h(", ".join(missing)))
    rows += [[(r.L("➕ Papka qo'shish", "➕ Добавить папку"), "cfa"), (r.L("🔄 Telegram'dan", "🔄 Из Telegram"), "cfs")],
             nav(r, "c")]
    return ui.join(title("📁", r.L("PAPKALAR", "ПАПКИ")), "", card(note)), kb(*rows)


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
    lines = [f"👤 {r.L('Xodimlar', 'Сотрудники')} — " + (h(", ".join(P.mention(p) for p in ppl)) or
                                                         r.L("belgilanmagan ⚠️", "не назначены ⚠️")),
             f"💬 {r.L('Chatlar', 'Чаты')} — <b>{chats}</b>",
             f"🚨 {r.L('Zaderjka nazorati', 'Контроль задержек')} — {onoff(r, f['delay_on'])}",
             f"💸 {r.L('Jarima', 'Штраф')} — {folder_fine_text(ctx, r, f)}"
             + ("" if ctx.db.flag("fines_enabled") else r.L(" · ⚪ jarimalar o'chiq", " · ⚪ штрафы выключены"))]
    rows = grid([(f"👤 {r.L('Xodimlar', 'Сотрудники')}", f"cfp:{fid}"), (f"💬 {r.L('Chatlar', 'Чаты')}", f"cfc:{fid}"),
                 (f"💸 {r.L('Jarima', 'Штраф')}", f"cff:{fid}"),
                 ((r.L("⛔ Nazorat o'ch", "⛔ Выкл. контроль") if f["delay_on"] else r.L("✅ Nazorat yoq",
                                                                                       "✅ Вкл. контроль")),
                  f"cfd:{fid}"),
                 (f"✏️ {r.L('Nomi', 'Название')}", f"cfr:{fid}"), (f"🗑 {r.L('O‘chirish', 'Удалить')}", f"cfx:{fid}")])
    rows.append(nav(r, "cf"))
    return ui.join(title("📁", h(f["name"])), "", card(lines)), kb(*rows)


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
