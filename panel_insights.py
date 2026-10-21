"""📈 Tahlil ekranlari (📊 Hisobotlar → 📈 Tahlil) va 🧩 qo'shimcha funksiyalarni yoqish/o'chirish."""
from __future__ import annotations

from . import insights as I
from . import people as P
from . import ui
from .insights import dur, pct
from .ui import Req, card, grid, h, kb, nav, on_input, onoff, screen, title

# (kalit, belgi, to'liq nomi uz/ru, tugmadagi qisqa nomi uz/ru)
TOGGLES = (("an_heatmap", "🕐", "Soatlar (talab xaritasi)", "Часы (карта спроса)", "Soatlar", "Часы"),
           ("an_stale", "💤", "Qotib qolgan lidlar", "Застывшие лиды", "Qotib qolgan", "Застывшие"),
           ("an_cooling", "📉", "Soviyotgan lidlar", "Остывающие лиды", "Soviyotgan", "Остывающие"),
           ("cool_auto", "🔔", "Soviyotganlarni «Проёб»da eslatish", "Напоминать об остывающих в «Проёб»",
            "Eslatma «Проёб»da", "Напоминание в «Проёб»"),
           ("an_speed", "⚡", "Javob tezligi va g'oliblar", "Скорость ответа и лидеры", "Tezlik, g'oliblar",
            "Скорость, лидеры"),
           ("an_cards", "💳", "Kartalar (RD bo'yicha)", "Карты (по RD)", "Kartalar", "Карты"),
           ("an_push", "📣", "Push natijasi", "Результат Пуша", "Push natijasi", "Результат Пуша"),
           ("spam_check", "🛡", "Akkauntlarni @SpamBot da tekshirish", "Проверка аккаунтов в @SpamBot",
            "@SpamBot", "@SpamBot"),
           ("delay_batch", "🧲", "Yaqin zaderjkalarni birlashtirish (40 s)", "Объединять близкие задержки (40 с)",
            "Birlashtirish 40 s", "Объединять 40 с"))


def now_of(ctx) -> int:
    return int(ctx.clock())


def rd_buttons(r: Req, ctx, prefix: str, counts: dict | None = None, cur: int | None = None) -> list:
    btn = []
    for f in P.folders(ctx.db):
        n = (counts or {}).get(f["id"])
        if counts is not None and not n:
            continue
        mark = "✅ " if cur == f["id"] else ""
        btn.append((f"{mark}📁 {f['name']}" + (f" · {n}" if n else ""), f"{prefix}:{f['id']}"))
    return grid(btn, 2)


# ───────────────────────── menyu
@screen("an", "full")
async def menu(ctx, r: Req):
    db = ctx.db
    items = [("an_heatmap", r.L("🕐 Soatlar", "🕐 Часы"), "anh:td:0"),
             ("an_stale", r.L("💤 Qotib qolgan", "💤 Застывшие"), "anst"),
             ("an_cooling", r.L("📉 Soviyotgan", "📉 Остывающие"), "anc"),
             ("an_speed", r.L("⚡ Tezlik → karta", "⚡ Скорость → карта"), "ansp"),
             ("an_speed", r.L("🏆 G'oliblar", "🏆 Лидеры"), "anw"),
             ("an_cards", r.L("💳 Kartalar", "💳 Карты"), "ank:td"),
             ("an_push", r.L("📣 Push natijasi", "📣 Результат Пуша"), "uh")]
    btn = [(lab, data) for key, lab, data in items if db.flag(key)]
    lines = [r.L("Hammasi faqat vaqt va kim yozgani bo'yicha — xabar matni o'qilmaydi.",
                 "Всё считается только по времени и автору — текст сообщений не читается."),
             r.L(f"💳 Karta — xodim topikda <code>{h(_cmds(ctx))}</code> buyrug'ini yozdi. "
                 f"Ma'lumot {h(_since(ctx))} dan yig'ilmoqda.",
                 f"💳 Карта — сотрудник написал в топике команду <code>{h(_cmds(ctx))}</code>. "
                 f"Данные собираются с {h(_since(ctx))}.")]
    if not btn:
        lines.append(r.L("Hammasi o'chiq — ⚙️ Sozlash orqali yoqing.", "Всё выключено — включите в ⚙️ Настройке."))
    rows = grid(btn, 2)
    if r.owner:
        rows.append([(r.L("⚙️ Sozlash (yoqish / o'chirish)", "⚙️ Настройка (вкл / выкл)"), "ans")])
    rows.append(nav(r, "r"))
    return ui.join(title("📈", r.L("TAHLIL", "АНАЛИТИКА")), "", card(lines)), kb(*rows)


def _cmds(ctx) -> str:
    return " ".join(sorted(ctx.tracker.card_cmds())) or "—"


def _since(ctx) -> str:
    from .timeutil import fmt
    ts = I.since_ts(ctx.db)
    return fmt(ts, ctx.tz) if ts else "—"


def _off(ctx, r: Req, key: str):
    if ctx.db.flag(key):
        return None
    return ui.join(title("📈", r.L("TAHLIL", "АНАЛИТИКА")), "", card(
        [r.L("Bu funksiya o'chiq. ⚙️ Sozlash orqali yoqish mumkin.", "Эта функция выключена. Включается в ⚙️ Настройке.")])), \
        kb(nav(r, "an"))


# ───────────────────────── 🕐 soatlar
@screen("anh", "full")
async def hours(ctx, r: Req):
    off = _off(ctx, r, "an_heatmap")
    if off:
        return off
    key = r.args[0] if r.args and r.args[0] in ("td", "7d") else "td"
    fid = int(r.args[1]) if len(r.args) > 1 and r.args[1].lstrip("-").isdigit() else 0
    s, e = I.period(now_of(ctx), ctx.tz, key)
    data = I.heatmap(ctx.db, ctx.tracker, s, e, fid or None)
    f = P.folder(ctx.db, fid) if fid else None
    sub = (r.L("bugun", "сегодня") if key == "td" else r.L("oxirgi 7 kun", "последние 7 дней")) + \
        f" · {h(f['name']) if f else r.L('hamma RD', 'все RD')}"
    lines = I.heatmap_text(data, r.lang) + [r.L(
        "<i>Har soat: nechta lid yozdi (bir lid bir soatda bir marta sanaladi) · 🚨 shu soatda yozib, zaderjkaga "
        "tushganlari.</i>",
        "<i>Каждый час: сколько лидов писали (лид в час считается один раз) · 🚨 сколько из них ушли в задержку.</i>")]
    other = "7d" if key == "td" else "td"
    rows = [[(r.L("🗓 7 kun", "🗓 7 дней") if other == "7d" else r.L("📅 Bugun", "📅 Сегодня"), f"anh:{other}:{fid}")]]
    btn = [(("✅ " if not fid else "") + r.L("Hamma RD", "Все RD"), f"anh:{key}:0")] + \
        [(("✅ " if fid == x["id"] else "") + f"📁 {x['name']}", f"anh:{key}:{x['id']}") for x in P.folders(ctx.db)]
    rows += grid(btn, 2)
    rows.append(nav(r, "an"))
    return ui.join(title("🕐", r.L("SOATLAR", "ЧАСЫ"), sub), "", card(lines)), kb(*rows)


# ───────────────────────── 💤 qotib qolgan / 📉 soviyotgan
def _list_screen(ctx, r: Req, kind: str):
    db = ctx.db
    key = "an_stale" if kind == "stale" else "an_cooling"
    off = _off(ctx, r, key)
    if off:
        return off
    days = max(1, db.get_int("stale_days" if kind == "stale" else "cooling_days", 3 if kind == "stale" else 2))
    now = now_of(ctx)
    data = I.stale(db, ctx.tracker, now, days) if kind == "stale" else I.cooling(db, ctx.tracker, now, days)
    prefix = "anst" if kind == "stale" else "anc"
    fid = int(r.args[0]) if r.args and r.args[0].isdigit() else 0
    if kind == "stale":
        head = title("💤", r.L("QOTIB QOLGAN LIDLAR", "ЗАСТЫВШИЕ ЛИДЫ"),
                     r.L(f"{days}+ kun hech kim yozmagan", f"{days}+ дн. никто не писал"))
        how = r.L(f"<i>{days} kundan beri na mijoz, na xodim yozmagan (Push hisobga kirmaydi), oxirgi 30 kunda "
                  "gaplashilgan. ⚡/💊 kirmaydi. 💳 — karta yuborilgan · ❗ — mijoz yozgan, javob yo'q.</i>",
                  f"<i>{days} дн. не писали ни клиент, ни сотрудник (Пуш не считается), общались за последние 30 дней. "
                  "⚡/💊 не входят. 💳 — карта отправлялась · ❗ — клиент писал, ответа нет.</i>")
    else:
        head = title("📉", r.L("SOVIYOTGAN LIDLAR", "ОСТЫВАЮЩИЕ ЛИДЫ"),
                     r.L(f"{days} kungacha kuzatiladi", f"следим до {days} дн."))
        how = r.L("<i>Xodim yozgan, mijoz odatdagidan 3 barobar (kamida 1 soat) uzoq jim. Vaqt ish vaqtida hisoblanadi "
                  f"(tun kirmaydi). {days} kundan keyin — «qotib qolgan»ga o'tadi. 💳 — karta yuborilgan.</i>",
                  "<i>Сотрудник написал, клиент молчит в 3 раза дольше обычного (минимум 1 час). Время — рабочее "
                  f"(ночь не считается). Через {days} дн. — переходит в «застывшие». 💳 — карта отправлялась.</i>")
    rows = []
    if fid:
        f = P.folder(db, fid)
        items = data.get(fid) or []
        line = I.stale_line if kind == "stale" else I.cooling_line
        lines = [f"<b>📁 {h(f['name']) if f else '?'}</b> — <b>{len(items)}</b>"] + \
            [line(x, r.lang) for x in items[:40]]
        if len(items) > 40:
            lines.append(r.L(f"… yana {len(items) - 40}", f"… ещё {len(items) - 40}"))
        body = ui.join(head, "", card(lines), how)
        rows.append([(r.L("📤 «Проёб»ga yuborish", "📤 Отправить в «Проёб»"), f"{prefix}x:{fid}")])
        rows.append(nav(r, prefix))
        return body, kb(*rows)
    counts = {k: len(v) for k, v in data.items()}
    total = sum(counts.values())
    lines = [f"📁 {h(f['name'])} — <b>{counts.get(f['id'], 0)}</b>" for f in P.folders(db)] or \
        [r.L("Papka yo'q", "Нет папок")]
    lines.append(r.L(f"Jami — <b>{total}</b>", f"Всего — <b>{total}</b>"))
    rows += rd_buttons(r, ctx, prefix, counts)
    if total:
        rows.append([(r.L("📤 Hammasini «Проёб»ga (har RD alohida)", "📤 Всё в «Проёб» (каждая RD отдельно)"),
                      f"{prefix}x:0")])
    rows.append(nav(r, "an"))
    return ui.join(head, "", card(lines), how), kb(*rows)


@screen("anst", "full")
async def stale_screen(ctx, r: Req):
    return _list_screen(ctx, r, "stale")


@screen("anc", "full")
async def cooling_screen(ctx, r: Req):
    return _list_screen(ctx, r, "cool")


async def post_lists(ctx, kind: str, fid: int = 0) -> int:
    """«Проёб»ga: har RD alohida xabar. -> nechta xabar ketdi."""
    db = ctx.db
    days = max(1, db.get_int("stale_days" if kind == "stale" else "cooling_days", 3 if kind == "stale" else 2))
    now = now_of(ctx)
    data = I.stale(db, ctx.tracker, now, days) if kind == "stale" else I.cooling(db, ctx.tracker, now, days)
    if fid:
        data = {fid: data.get(fid) or []}
    n = 0
    for text in I.group_messages(db, kind, data, days):
        await ctx.notifier.send_group(text)
        n += 1
    return n


async def _post(ctx, r: Req, kind: str):
    ui.effect()
    fid = int(r.args[0]) if r.args and r.args[0].isdigit() else 0
    try:
        n = await post_lists(ctx, kind, fid)
    except Exception:
        n = -1
    msg = (r.L(f"📤 «Проёб»ga yuborildi: {n} ta xabar", f"📤 Отправлено в «Проёб»: {n}") if n > 0 else
           r.L("Yuboradigan narsa yo'q", "Нечего отправлять") if n == 0 else
           r.L("⚠️ «Проёб»ga yozib bo'lmadi", "⚠️ Не удалось написать в «Проёб»"))
    await ui.toast(ctx.bot, r.chat_id, msg)
    r.args = [str(fid)] if fid else []
    ui.view(r, ("anst" if kind == "stale" else "anc") + (f":{fid}" if fid else ""))
    return _list_screen(ctx, r, kind)


@screen("anstx", "full")
async def stale_post(ctx, r: Req):
    return await _post(ctx, r, "stale")


@screen("ancx", "full")
async def cooling_post(ctx, r: Req):
    return await _post(ctx, r, "cool")


# ───────────────────────── ⚡ tezlik → karta
@screen("ansp", "full")
async def speed(ctx, r: Req):
    off = _off(ctx, r, "an_speed")
    if off:
        return off
    d = I.speed_outcome(ctx.db, ctx.tracker, now_of(ctx))
    head = title("⚡", r.L("JAVOB TEZLIGI → KARTA", "СКОРОСТЬ ОТВЕТА → КАРТА"),
                 r.L(f"oxirgi 30 kun · {d['total']} lid", f"последние 30 дней · {d['total']} лидов"))
    if d["total"] < 20:
        body = [r.L(f"Ma'lumot yig'ilmoqda: hozir {d['total']} lid (kamida 20 kerak). Lid birinchi yozganidan 3 kun "
                    "o'tgach hisobga kiradi — natijasi aniq bo'lishi uchun.",
                    f"Данные собираются: сейчас {d['total']} лидов (нужно минимум 20). Лид входит через 3 дня после "
                    "первого сообщения — чтобы результат был точным.")]
    else:
        w = r.L("daq", "мин")
        rows = [f"{lab:>6} {w:<3} {n:>4}   {c:>4} ({pct(c, n)})" for lab, n, c in d["rows"]]
        head_row = r.L("javob        lid  kartagacha", "ответ        лиды  до карты")
        body = ["<pre>" + head_row + "\n" + "\n".join(rows) + "</pre>"]
        if d["none"][0]:
            body.append(r.L(f"Javob kutmagan (xodim o'zi boshlagan yoki tunda yozgan): {d['none'][0]} lid, kartagacha "
                            f"{d['none'][1]}", f"Без ожидания ответа (начал сотрудник или писали ночью): "
                            f"{d['none'][0]}, до карты {d['none'][1]}"))
        fast, slow = d["rows"][0], d["rows"][-1]
        if fast[1] and slow[1] and slow[2]:
            k = (fast[2] / fast[1]) / (slow[2] / slow[1])
            body.append(r.L(f"Xulosa: 5 daqiqagacha javob olganlar 20+ daqiqada javob olganlarga qaraganda "
                            f"<b>{k:.1f} barobar</b> ko'p kartagacha yetgan.",
                            f"Вывод: получившие ответ до 5 минут доходят до карты в <b>{k:.1f} раза</b> чаще, "
                            "чем ждавшие 20+ минут."))
    how = r.L("<i>Lid birinchi yozgandan 3 kun ichida karta olsa — «kartagacha yetdi». Javob tezligi — kartagacha "
              "bo'lgan javoblar o'rtachasi, ish vaqtida.</i>",
              "<i>Карта в течение 3 дней после первого сообщения — «дошёл до карты». Скорость — среднее время ответа "
              "до карты, в рабочее время.</i>")
    return ui.join(head, "", card(body), how), kb([(r.L("🏆 G'oliblar", "🏆 Лидеры"), "anw")], nav(r, "an"))


# ───────────────────────── 🏆 g'oliblar
@screen("anw", "full")
async def leaders(ctx, r: Req):
    off = _off(ctx, r, "an_speed")
    if off:
        return off
    d = I.winners(ctx.db, ctx.tracker, now_of(ctx))
    lines = []
    for x in d["rows"]:
        lines.append(f"<b>{h(x['p']['name'])}</b> — {x['leads']} {r.L('lid', 'лид.')} · 💳 {x['cards']} "
                     f"({pct(x['cards'], x['leads'])}) · {r.L('javob', 'ответ')} ~{dur(x['reply'], r.lang)} · "
                     f"{r.L('kartagacha', 'до карты')} ~{dur(x['to_card'], r.lang)}")
    if d["unknown"]:
        lines.append(r.L(f"❔ Aniqlanmagan (papka akkaunti, papkada bir nechta xodim): {d['unknown']['replies']} javob, "
                         f"💳 {d['unknown']['cards']}",
                         f"❔ Не определено (аккаунт папки, в папке несколько сотрудников): {d['unknown']['replies']} "
                         f"ответов, 💳 {d['unknown']['cards']}"))
    if not lines:
        lines = [r.L("Ma'lumot yig'ilmoqda.", "Данные собираются.")]
    parts = [title("🏆", r.L("G'OLIBLAR", "ЛИДЕРЫ"), r.L("oxirgi 30 kun", "последние 30 дней")), "", card(lines)]
    fm = d["formula"]
    if fm:
        parts.append(card([
            f"<b>{r.L('🏆 Formula', '🏆 Формула')}</b>",
            f"🥇 {h(', '.join(fm['best']))}: 💳 {fm['best_conv'] * 100:.0f}% · "
            f"{r.L('javob', 'ответ')} ~{dur(fm['best_reply'], r.lang)} · {r.L('kartagacha', 'до карты')} "
            f"~{dur(fm['best_card'], r.lang)}",
            f"{r.L('Qolganlar', 'Остальные')}: 💳 {fm['rest_conv'] * 100:.0f}% · "
            f"{r.L('javob', 'ответ')} ~{dur(fm['rest_reply'], r.lang)} · {r.L('kartagacha', 'до карты')} "
            f"~{dur(fm['rest_card'], r.lang)}"]))
    else:
        parts.append(card([r.L(f"Formula uchun kamida 2 xodimda {I.MIN_LEADS} tadan lid bo'lishi kerak.",
                               f"Для формулы нужно минимум 2 сотрудника с {I.MIN_LEADS}+ лидами.")]))
    parts.append(r.L("<i>Lid — xodim javob bergan yoki karta yuborgan topik. Javob va kartagacha vaqt — mediana (odatdagi "
                     "qiymat), ish vaqtida. Papka akkauntidan yozilsa — papkada bitta xodim bo'lsa, unga yoziladi.</i>",
                     "<i>Лид — топик, где сотрудник ответил или отправил карту. Время ответа и до карты — медиана "
                     "(обычное значение), в рабочее время. С аккаунта папки — засчитывается, если в папке один "
                     "сотрудник.</i>"))
    return ui.join(*parts), kb([(r.L("⚡ Tezlik → karta", "⚡ Скорость → карта"), "ansp")], nav(r, "an"))


# ───────────────────────── 💳 kartalar
@screen("ank", "full")
async def cards(ctx, r: Req):
    off = _off(ctx, r, "an_cards")
    if off:
        return off
    key = r.args[0] if r.args and r.args[0] in ("td", "yd", "7d") else "td"
    fid = int(r.args[1]) if len(r.args) > 1 and r.args[1].isdigit() else 0
    s, e = I.period(now_of(ctx), ctx.tz, key)
    data = I.cards_report(ctx.db, ctx.tracker, s, e)
    names = {"td": r.L("bugun", "сегодня"), "yd": r.L("kecha", "вчера"), "7d": r.L("oxirgi 7 kun", "последние 7 дней")}
    head = title("💳", r.L("KARTALAR", "КАРТЫ"), names[key])
    rows = [[(("✅ " if k == key else "") + lab, f"ank:{k}:{fid}") for k, lab in
             (("td", r.L("Bugun", "Сегодня")), ("yd", r.L("Kecha", "Вчера")), ("7d", r.L("7 kun", "7 дней")))]]
    if fid:
        f = P.folder(ctx.db, fid)
        d = data.get(fid) or {"total": 0, "leads": []}
        lines = [f"<b>📁 {h(f['name']) if f else '?'}</b> — 💳 <b>{d['total']}</b> {r.L('marta', 'раз')} · "
                 f"{len(d['leads'])} {r.L('lid', 'лид.')}"]
        lines += [f"{h(x['link'])} — <b>{x['n']}</b> {r.L('marta', 'раз')}" for x in d["leads"][:40]]
        if len(d["leads"]) > 40:
            lines.append(r.L(f"… yana {len(d['leads']) - 40}", f"… ещё {len(d['leads']) - 40}"))
        rows.append(nav(r, f"ank:{key}"))
        return ui.join(head, "", card(lines)), kb(*rows)
    lines = []
    for f in P.folders(ctx.db):
        d = data.get(f["id"])
        lines.append(f"📁 {h(f['name'])} — 💳 <b>{d['total'] if d else 0}</b> {r.L('marta', 'раз')} · "
                     f"{len(d['leads']) if d else 0} {r.L('lid', 'лид.')}")
    total = sum(d["total"] for d in data.values())
    lines.append(r.L(f"Jami — <b>{total}</b>", f"Всего — <b>{total}</b>"))
    rows += grid([(f"📁 {f['name']}", f"ank:{key}:{f['id']}") for f in P.folders(ctx.db) if data.get(f["id"])], 2)
    rows.append(nav(r, "an"))
    return ui.join(head, "", card(lines), r.L(
        f"<i>Karta — xodim topikda <code>{h(_cmds(ctx))}</code> buyrug'ini yozgan. Buyruqlarni o'zgartirish: "
        "⚙️ Sozlamalar → 🧩 → 💳.</i>",
        f"<i>Карта — сотрудник написал в топике команду <code>{h(_cmds(ctx))}</code>. Изменить команды: "
        "⚙️ Настройки → 🧩 → 💳.</i>")), kb(*rows)


# ───────────────────────── 🧩 yoqish / o'chirish
@screen("ans", "owner")
async def settings(ctx, r: Req):
    db = ctx.db
    if len(r.args) > 1 and r.args[0] == "t" and r.args[1] in {k for k, *_ in TOGGLES}:
        db.toggle(r.args[1])
    lines = []
    btn = []
    for key, icon, uz, ru, short_uz, short_ru in TOGGLES:
        extra = ""
        if key == "an_stale":
            extra = f" · {db.get_int('stale_days', 3)} {r.L('kun', 'дн.')}"
        elif key == "an_cooling":
            extra = f" · {db.get_int('cooling_days', 2)} {r.L('kungacha', 'дн.')}"
        elif key == "an_push":
            extra = f" · {db.get_int('push_reply_min', 90)} {r.L('daq', 'мин')}"
        lines.append(f"{icon} {r.L(uz, ru)} — {onoff(r, db.flag(key))}{extra}")
        btn.append((f"{'🟢' if db.flag(key) else '⚪'} {icon} {r.L(short_uz, short_ru)}", f"ans:t:{key}"))
    lines.append(f"💳 {r.L('Karta buyruqlari', 'Команды карты')} — <code>{h(_cmds(ctx))}</code>")
    rows = grid(btn, 2)
    rows.append([(f"💳 {r.L('Karta buyruqlari', 'Команды карты')}", "ansk")])
    rows.append([(f"💤 {db.get_int('stale_days', 3)} {r.L('kun', 'дн.')}", "ansd:stale"),
                 (f"📉 {db.get_int('cooling_days', 2)} {r.L('kun', 'дн.')}", "ansd:cool"),
                 (f"📣 {db.get_int('push_reply_min', 90)} {r.L('daq', 'мин')}", "ansd:push")])
    rows.append(nav(r, "an"))
    hint = r.L("🟢 — yoniq, ⚪ — o'chiq. Tugmani bossangiz — o'zgaradi. Pastki qatordagi raqamlar — kunlar va "
               "daqiqalar (bosib o'zgartiring).",
               "🟢 — вкл, ⚪ — выкл. Нажмите кнопку — переключится. Нижний ряд — дни и минуты (нажмите, чтобы "
               "изменить).")
    return ui.join(title("🧩", r.L("QO'SHIMCHA FUNKSIYALAR", "ДОП. ФУНКЦИИ")), "", card(lines), card([hint])), kb(*rows)


@screen("ansk", "owner")
async def card_cmds_ask(ctx, r: Req):
    """💳 Karta buyruqlari (hamma RD uchun). CRM egasi buyruqni o'zgartirsa — shu yerda yangilanadi."""
    ui.ask(r, "card_cmds", "ans")
    return ui.join(title("💳", r.L("KARTA BUYRUQLARI", "КОМАНДЫ КАРТЫ")), "", card(
        [r.L(f"Hozir: <code>{h(_cmds(ctx))}</code>", f"Сейчас: <code>{h(_cmds(ctx))}</code>"),
         r.L("Xodim lidga karta yuborganda topikda yozadigan buyruqlarni yuboring (bo'sh joy bilan). Hamma RD uchun.",
             "Пришлите команды, которыми сотрудник отправляет лиду карту (через пробел). Для всех RD."),
         r.L("Masalan: <code>/rek /dep /cash</code>", "Например: <code>/rek /dep /cash</code>"),
         r.L("Bot shu buyruqni ko'rsa — «lidga karta ketdi» deb yozib oladi. Xabar matni o'qilmaydi.",
             "Увидев команду, бот записывает «лиду отправлена карта». Текст сообщений не читается.")])), \
        ui.cancel_kb(r, "ans")


@on_input("card_cmds", "owner")
async def card_cmds_set(ctx, r: Req):
    from .rules import parse_cmds
    cmds = parse_cmds(r.text)
    if not cmds or len(cmds) > 10:
        return r.L("⚠️ Masalan: /rek /dep /cash", "⚠️ Например: /rek /dep /cash")
    ctx.db.set("card_cmds", " ".join(sorted(cmds)))
    ui.WAIT.pop(r.uid, None)
    r.args = []
    ui.view(r, "ans")
    return await settings(ctx, r)


DAY_CHOICES = {"stale": ("stale_days", (2, 3, 4, 5, 7, 10)), "cool": ("cooling_days", (1, 2, 3, 4, 5)),
               "push": ("push_reply_min", (30, 40, 60, 90, 120, 180))}


@screen("ansd", "owner")
async def choose(ctx, r: Req):
    what = r.args[0] if r.args and r.args[0] in DAY_CHOICES else "stale"
    key, opts = DAY_CHOICES[what]
    if len(r.args) > 1 and r.args[1].isdigit() and int(r.args[1]) in opts:
        ctx.db.set(key, r.args[1])
        r.args = []
        return await settings(ctx, r)
    cur = ctx.db.get_int(key)
    unit = r.L("daq", "мин") if what == "push" else r.L("kun", "дн.")
    ask = {"stale": r.L("Necha kun hech kim yozmasa — «qotib qolgan»?", "Сколько дней без переписки — «застывший»?"),
           "cool": r.L("Soviyotgan lid necha kungacha kuzatilsin (keyin — «qotib qolgan»)?",
                       "Сколько дней следить за остывающим (потом — «застывший»)?"),
           "push": r.L("Push'dan keyin necha daqiqa ichida yozsa — «Push'ga javob»?",
                       "Сколько минут после Пуша считать ответом на Пуш?")}[what]
    rows = grid([(("✅ " if v == cur else "") + f"{v} {unit}", f"ansd:{what}:{v}") for v in opts], 3)
    rows.append(nav(r, "ans"))
    return ui.join(title("🧩", r.L("SOZLASH", "НАСТРОЙКА")), "", card([ask])), kb(*rows)
