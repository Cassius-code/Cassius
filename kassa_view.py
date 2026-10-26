"""Kassa matnlari: panel (uz/ru, HTML, premium kartochkalar) va xodimga xabar (ruscha, faqat o'z zp si).

Maxfiylik: egasining ulushi va akkauntlar bo'yicha daromad faqat egaga (owner=True). Adminlarga ham ko'rinmaydi.
Xodimga: faqat zp (o'z foizi), jarima, bonus, avans, jami — kassa $ va boshqalarning raqamlari yo'q.
"""
from __future__ import annotations

import datetime as dt
import html

from .kassa import r2

W = {
    "kassa": ("Kassa", "Касса"), "zp": ("Zp", "Зп"), "checks": ("chek", "чек."), "total": ("Jami", "Итого"),
    "fine": ("jarima", "штраф"), "bonus": ("bonus", "бонус"), "adv": ("avans", "аванс"),
    "from_acct": ("akkauntidan", "с аккаунта"), "pool": ("umumiy akkaunt", "общий аккаунт"),
    "zp_off": ("zp hisoblanmaydi", "зп не считается"), "transfer_out": ("o'tkazdi →", "перенос →"),
    "transfer_in": ("dan o'tkazma", "перенос от"), "share_in": ("ulush", "доля"), "share_out": ("ulush beradi →",
                                                                                                  "отдаёт долю →"),
    "you": ("Siz", "Вы"), "only_you": ("faqat sizga ko'rinadi", "видно только вам"),
    "partner": ("Artur", "Артур"), "half": ("Sizning yarmingiz", "Ваша половина"), "zps": ("Xodimlar zp si",
                                                                                          "Зарплаты"),
    "shares": ("Ulushlar (siz to'laysiz)", "Доли (платите вы)"), "share_s": ("ulush", "доля"), "income": ("Daromadingiz", "Ваш доход"),
    "by_acct": ("Akkauntlar bo'yicha", "По аккаунтам"), "to_you": ("sizga", "вам"),
    "fines_pl": ("jarimalar", "штрафы"), "bonuses_pl": ("bonuslar", "бонусы"), "no_data": ("Ma'lumot yo'q",
                                                                                           "Данных нет"),
    "unassigned": ("chekda kim ishlagani belgilanmagan", "чек(ов) без исполнителя"),
    "noprice": ("chek narxsiz", "чек(ов) без цены"), "report": ("KASSA HISOBOTI", "ОТЧЁТ ПО КАССЕ"),
    "unknown_zp": ("zp hisoblanmaganlar (o'zingiz hisoblaysiz)", "без расчёта зп (считаете сами)"),
    "own": ("o'z akkaunti", "свой аккаунт"), "rating": ("REYTING", "РЕЙТИНГ"),
    "check": ("Tekshiruv", "Проверка"), "all_ok": ("hammasi taqsimlandi", "всё распределено"),
    "transfers": ("o'tkazmalar", "переносы"), "vs": ("solishtirish", "сравнение"),
    "rest": ("qoldig'i", "остаток"), "worked": ("ishlagan", "работал"), "by_price": ("prays bo'yicha", "по прайсу"), "after_artur": ("Arturdan keyin", "После Артура"),
    "pshares": ("ulushlar (Artur to'laydi)", "доли (платит Артур)"),
    "not_calc": ("🧮 Zp hali hisoblanmagan", "🧮 Зп ещё не рассчитана"),
    "zp_off_all": ("🧮 Zp hisoblash o'chiq — o'zingiz hisoblaysiz", "🧮 Расчёт зп выключен — считаете сами"),
    "adjs": ("Jarima · bonus · avans", "Штрафы · бонусы · авансы"),
}


def w(key: str, lang: str) -> str:
    uz, ru = W[key]
    return ru if lang == "ru" else uz


def h(s) -> str:
    return html.escape(str(s), quote=False)


def money(v) -> str:
    v = r2(v or 0)
    s = f"{v:,.2f}".replace(",", " ")
    return s[:-3] if s.endswith(".00") else s


def num(v) -> str:
    return f"{int(v):,}".replace(",", " ")


def dshort(d: str | dt.date) -> str:
    d = dt.date.fromisoformat(d) if isinstance(d, str) else d
    return d.strftime("%d.%m")


def label(s: dt.date, e: dt.date) -> str:
    return dshort(s) if s == e else f"{dshort(s)} – {dshort(e)}"


def pct(v) -> str:
    return f"{float(v):g}%"


def card(lines: list[str], expandable: bool = False) -> str:
    lines = [ln for ln in lines if ln is not None]
    if not lines:
        return ""
    tag = "<blockquote expandable>" if expandable else "<blockquote>"
    return tag + "\n".join(lines) + "</blockquote>"


# ───────────────────────── zp tafsiloti (bitta odam)
def adj_lines(r: dict, lang: str) -> list[str]:
    out = []
    for key, sign in (("fines", "−"), ("bonuses", "+"), ("advs", "−")):
        word = {"fines": "fine", "bonuses": "bonus", "advs": "adv"}[key]
        for x in r[key]:
            note = f" · {h(x['note'])}" if x["note"] else ""
            out.append(f"{sign} {w(word, lang)} {money(x['usd'])} $ ({dshort(x['day'])}{note})")
    return out


def zp_lines(b: dict, r: dict, lang: str, owner: bool, zp: bool = True) -> list[str]:
    """Formulalar: 489 $ × 41% = 200.49 $; boshqa akkauntdan; jarima/bonus/avans; o'tkazma/ulush; jami.
    zp=False — hafta hali hisoblanmagan: faqat jarima/bonus/avans."""
    names = b["names"]
    out: list[str] = []
    if not zp:
        return [f"<i>{w('not_calc', lang)}</i>"] + adj_lines(r, lang)
    if r["kind"] == "partner":
        o = b["owner"]
        if o["partner_pct"] is not None:
            out.append(f"{w('kassa', lang)} {money(b['K'])} $ × {pct(o['partner_pct'])} = "
                       f"{money(r['share_part'] + o['partner_paid'])} $")
        else:
            for a in o["per_acct"]:
                if a["artur"] + a["pshare"]:
                    out.append(f"{h(names.get(a['pid'], '?'))} {w('rest', lang)}: {money(a['artur'] + a['pshare'])} $")
        if o["partner_paid"]:
            out.append(f"− {w('pshares', lang)} {money(o['partner_paid'])} $")
        if r["pf"]:
            out.append(f"+ {w('fines_pl', lang)} {money(r['pf'])} $")
        if r["pb"]:
            out.append(f"− {w('bonuses_pl', lang)} {money(r['pb'])} $")
    elif r["zp_on"]:
        own = [(acct, p, u) for (acct, p), u in r["earn"].items() if acct == r["p"]["id"]]
        other = [(acct, p, u) for (acct, p), u in r["earn"].items() if acct != r["p"]["id"]]
        for _a, p, u in own:
            out.append(f"{money(u)} $ × {pct(p)} = {money(u * p / 100)} $")
        for acct, p, u in other:
            out.append(f"+ {h(names.get(acct, '?'))} {w('from_acct', lang)}: {money(u)} $ × {pct(p)} = "
                       f"{money(u * p / 100)} $")
    else:
        out.append(f"<i>{w('zp_off', lang)}</i>")
    out += adj_lines(r, lang)
    for o in r["outs"]:
        out.append(f"− {w('transfer_out', lang)} {h(names.get(o['other'], '?'))} ({dshort(o['day'])}, {pct(o['pct'])}) "
                   f"{money(o['amount'])} $")
    for i in r["ins"]:
        out.append(f"+ {h(names.get(i['other'], '?'))} {w('transfer_in', lang)} ({dshort(i['day'])}, {pct(i['pct'])}) "
                   f"{money(i['amount'])} $")
    for i in r["sin"]:
        base = w("kassa", lang).lower() if i["base"] == "kassa" else w("zp", lang).lower()
        out.append(f"+ {w('share_in', lang)} {pct(i['pct'])} · {h(names.get(i['other'], '?'))} {base} = "
                   f"{money(i['amount'])} $")
    for i in r["sout"]:
        out.append(f"− {w('share_out', lang)} {h(names.get(i['other'], '?'))} {pct(i['pct'])} = {money(i['amount'])} $")
    if r["total"] is not None:
        out.append(f"= <b>{money(r['total'])} $</b>")
    return out


def kassa_line(r: dict, lang: str) -> str:
    """Kassa = cheklar yig'indisi (asosiy raqam); $ — prays bo'yicha (zp shundan)."""
    return f"{num(r['n'])} {w('checks', lang)} · <b>{num(r['raw'])}</b>"


def arrow(cur: float, prev: float | None) -> str:
    """↑12% / ↓5% — o'tgan davrning xuddi shu kunlariga nisbatan."""
    if prev is None or prev <= 0:
        return ""
    d = round((cur - prev) / prev * 100)
    if d == 0:
        return " <i>→0%</i>"
    return f" <i>{'↑' if d > 0 else '↓'}{abs(d)}%</i>"


def cmp_note(cmp: dict | None, lang: str) -> str | None:
    if not cmp or not cmp["PK"]:
        return None
    ps, pe = cmp["ps"], cmp["pe"]
    uz = f"↑↓ — {label(ps, pe)} ga nisbatan ({num(cmp['PK'])})"
    ru = f"↑↓ — к {label(ps, pe)} ({num(cmp['PK'])})"
    return f"<i>{ru if lang == 'ru' else uz}</i>"


# ───────────────────────── umumiy hisobot
def zp_note(zst: dict | None, lang: str, owner: bool = True) -> str | None:
    if not zst or zst["ready"]:
        return None
    if zst["mode"] == "off":
        return w("zp_off_all", lang)
    weeks = ", ".join(label(x, x + dt.timedelta(days=6)) for x in zst["weeks"])
    if owner:
        tail = {"uz": f"hafta: {weeks} — «🧮 Haftani hisoblash» ni bosing",
                "ru": f"неделя: {weeks} — нажмите «🧮 Рассчитать неделю»"}
    else:
        tail = {"uz": f"hafta: {weeks} — ega hisoblaydi", "ru": f"неделя: {weeks} — рассчитывает владелец"}
    return f"{w('not_calc', lang)}\n<i>{tail['ru' if lang == 'ru' else 'uz']}</i>"


def overall(b: dict, s: dt.date, e: dt.date, lang: str, owner: bool, cmp: dict | None = None,
            zst: dict | None = None) -> str:
    rows = [b["rows"][i] for i in b["order"] if i in b["rows"]]
    vis = [r for r in rows if owner or r["kind"] in ("worker", "pool")]
    parts = [f"<b>📊 {w('report', lang)}</b>", f"<i>{label(s, e)}</i>", ""]
    kl = []
    tn = traw = 0
    tusd = 0.0
    for r in vis:
        if r["kind"] == "partner" or not r["n"]:
            continue
        tag = f" <i>({w('pool', lang)})</i>" if r["kind"] == "pool" else ""
        up = arrow(cmp["cur"].get(r["p"]["id"], 0.0), cmp["prev"].get(r["p"]["id"])) if cmp else ""
        usd = f" · {money(r['usd'])} $" if owner else ""     # $ — faqat egaga
        kl.append(f"{h(r['p']['name'])}{tag} · {kassa_line(r, lang)}{usd}{up}")
        if r["unassigned"]:
            kl.append(f"   ⚠️ {r['unassigned']} {w('unassigned', lang)}")
        if r["noprice"]:
            kl.append(f"   ⚠️ {r['noprice']} {w('noprice', lang)}")
        tn, traw, tusd = tn + r["n"], traw + r["raw"], tusd + r["usd"]
    if not kl:
        return "\n".join(parts + [w("no_data", lang)])
    up = arrow(cmp["K"], cmp["PK"]) if cmp else ""
    kl.append(f"<b>{w('total', lang)}</b> · {num(tn)} {w('checks', lang)} · <b>{num(traw)}</b>"
              + (f" · <b>{money(tusd)} $</b>" if owner else "") + up)
    note = cmp_note(cmp, lang)
    if note:
        kl.append(note)
    parts.append(card([f"<b>💵 {w('kassa', lang)}</b>"] + kl))
    note = zp_note(zst, lang, owner)
    if note:
        parts.append(card([note]))
        al = []
        for r in vis:
            x = adj_lines(r, lang)
            if x:
                al.append(f"<b>{h(r['p']['name'])}</b>")
                al += ["   " + y for y in x]
        if al:
            parts.append(card([f"<b>⚠️ {w('adjs', lang)}</b>"] + al))
        return "\n".join(p for p in parts if p is not None)
    zl = []
    for r in vis:
        if r["kind"] not in ("worker", "self") or not (r["earn"] or r["fines"] or r["bonuses"] or r["advs"] or r["sin"]
                                                       or r["ins"] or r["outs"]):
            continue
        zl.append(f"<b>{h(r['p']['name'])}</b>")
        zl += ["   " + x for x in zp_lines(b, r, lang, owner)]
    if zl:
        parts.append(card([f"<b>💰 {w('zp', lang)}</b>"] + zl))
    if owner:
        parts.append(owner_card(b, lang))
    return "\n".join(p for p in parts if p is not None)


def owner_card(b: dict, lang: str) -> str:
    o = b["owner"]
    names = b["names"]
    ptag = f" {pct(o['partner_pct'])}" if o["partner_pct"] is not None else ""
    lines = [f"<b>💼 {w('you', lang)}</b> · <i>{w('only_you', lang)}</i>",
             f"{w('kassa', lang)}: <b>{num(b['raw'])}</b> → {money(o['K'])} $ <i>({w('by_price', lang)})</i>",
             f"{w('partner', lang)}{ptag}: {money(o['partner_share'])} $"
             + (f" + {w('fines_pl', lang)} {money(o['pf'])}" if o["pf"] else "")
             + (f" − {w('bonuses_pl', lang)} {money(o['pb'])}" if o["pb"] else "")
             + f" = <b>{money(o['partner_total'])} $</b>"]
    if o["partner_paid"]:
        lines.append(f"   ({w('pshares', lang)}: {money(o['partner_paid'])} $)")
    lines += [f"{w('half' if o['partner_pct'] is not None else 'after_artur', lang)}: {money(o['half'])} $",
              f"− {w('zps', lang)}: {money(o['zps'])} $"]
    if o["owner_paid"]:
        lines.append(f"− {w('shares', lang)}: {money(o['owner_paid'])} $")
    if o["out_self"]:
        lines.append(f"− {w('transfer_out', lang)} {money(o['out_self'])} $")
    if o["in_self"]:
        lines.append(f"+ {money(o['in_self'])} $")
    lines.append(f"= <b>{w('income', lang)}: {money(o['income'])} $</b>")
    lines.append("")
    lines += balance_lines(b, lang)
    if o["per_acct"]:
        lines.append("")
        lines.append(f"<b>{w('by_acct', lang)}</b>")
        for a in o["per_acct"]:
            nm = h(names.get(a["pid"], "?"))
            parts = [f"{w('partner', lang)} {money(a['artur'] + a['pshare'])}"]
            if a["zp"]:
                parts.append(f"{w('zp', lang).lower()} {money(a['zp'])}")
            if a["share"]:
                parts.append(f"{w('share_s', lang)} {money(a['share'])}")
            parts.append(f"{w('to_you', lang)} <b>{money(a['mine'])} $</b>")
            tag = f" ({w('you', lang).lower()})" if a["self"] else ""
            lines.append(f"{nm}{tag} · {money(a['usd'])} $ → " + " · ".join(parts))
    return card(lines, expandable=len(lines) > 14)


def balance_lines(b: dict, lang: str) -> list[str]:
    """🧮 Kassa = Artur + xodimlar + ulushlar + sizga — pul to'liq taqsimlanganini tekshirish (faqat egaga)."""
    o = b["owner"]
    mine = r2(o["income"] + o["out_self"] - o["in_self"])
    art = r2(o["partner_share"] + o["partner_paid"])
    tot = r2(art + o["zps"] + o["owner_paid"] + mine)
    ru = lang == "ru"
    parts = [f"{w('partner', lang)} {money(art)}", f"{'зп' if ru else 'xodimlar'} {money(o['zps'])}"]
    if o["owner_paid"]:
        parts.append(f"{w('share_s', lang)} {money(o['owner_paid'])}")
    parts.append(f"{w('to_you', lang)} {money(mine)}")
    issues = []
    noprice = sum(r["noprice"] for r in b["rows"].values())
    unassigned = sum(r["unassigned"] for r in b["rows"].values())
    if noprice:
        issues.append(f"⚠️ {noprice} {w('noprice', lang)}")
    if unassigned:
        issues.append(f"⚠️ {unassigned} {w('unassigned', lang)}")
    if o["unknown_zp"]:
        issues.append(f"⚠️ {w('unknown_zp', lang)}: {h(', '.join(o['unknown_zp']))}")
    if abs(tot - o["K"]) >= 0.05:
        issues.append(f"⚠️ {'разница' if ru else 'farq'} {money(o['K'] - tot)} $")
    mark = "⚠️" if issues else "✅"
    head = f"🧮 <b>{w('check', lang)}</b>: {money(o['K'])} = " + " + ".join(parts) + f" {mark}"
    if not issues:
        return [head]
    return [head] + issues


def owner_cabinet(b: dict, s: dt.date, e: dt.date, lang: str, me: dict | None, zst: dict | None = None) -> str:
    head = [f"<b>👑 {w('you', lang).upper()}</b>", f"<i>{label(s, e)}</i>", ""]
    parts = head
    ready = not zst or zst["ready"]
    if me is not None:
        parts.append(card([f"<b>💵 {w('kassa', lang)}</b>", kassa_line(me, lang)]) if me["n"] else "")
        parts.append(card([f"<b>💰 {w('zp', lang)}</b>"] + zp_lines(b, me, lang, True, ready)))
    if ready:
        parts.append(owner_card(b, lang))
    else:
        parts.append(card([zp_note(zst, lang)]))
    return "\n".join(p for p in parts if p)


def person_view(b: dict, r: dict, s: dt.date, e: dt.date, lang: str, owner: bool, zp: bool = True) -> str:
    """Xodim kartochkasidagi hisob (ega/admin uchun). Egasining ulushi bu yerda YO'Q."""
    parts = []
    if r["n"]:
        lines = [f"<b>💵 {w('kassa', lang)}</b>", kassa_line(r, lang)]
        if r["unassigned"]:
            lines.append(f"⚠️ {r['unassigned']} {w('unassigned', lang)}")
        names = b["names"]
        for payee, usd in r["paid_out"].items():
            lines.append(f"🔁 {w('worked', lang)}: {h(names.get(payee, '?'))}")
        parts.append(card(lines))
    zl = zp_lines(b, r, lang, owner, zp)
    if zl:
        parts.append(card([f"<b>💰 {w('zp', lang)}</b> · <i>{label(s, e)}</i>"] + zl))
    return "\n".join(parts) if parts else f"<i>{w('no_data', lang)}</i>"


# ───────────────────────── xodimga xabar (ruscha): faqat o'z zp si
def worker_message(r: dict, s: dt.date, e: dt.date, extra: str = "") -> str:
    lines = [f"💰 Зарплата · {label(s, e)}", ""]
    if r["zp_on"] and r["kind"] in ("worker", "self"):
        lines.append(f"Зп: {money(r['zp'])} $")
    for x in r["fines"]:
        lines.append(f"Штраф: −{money(x['usd'])} $ ({dshort(x['day'])}{' · ' + x['note'] if x['note'] else ''})")
    for x in r["bonuses"]:
        lines.append(f"Бонус: +{money(x['usd'])} $ ({dshort(x['day'])})")
    for x in r["advs"]:
        lines.append(f"Аванс: −{money(x['usd'])} $ ({dshort(x['day'])})")
    if r["zp_on"]:
        for o in r["outs"]:
            lines.append(f"Перенос: −{money(o['amount'])} $ ({dshort(o['day'])})")
        for i in r["ins"]:
            lines.append(f"Перенос: +{money(i['amount'])} $ ({dshort(i['day'])})")
        for i in r["sin"]:
            lines.append(f"Доля {pct(i['pct'])}: +{money(i['amount'])} $")
        for i in r["sout"]:
            lines.append(f"Доля: −{money(i['amount'])} $")
        if r["total"] is not None:
            lines += ["", f"Итого: {money(r['total'])} $"]
    if len(lines) == 2:
        lines.append("Начислений нет.")
    if extra:
        lines += ["", extra]
    return "\n".join(lines)


def rating(b: dict, s: dt.date, e: dt.date, lang: str) -> str:
    rows = sorted([r for r in b["rows"].values() if r["raw"] > 0 and r["kind"] in ("worker", "self", "pool")],
                  key=lambda r: -r["raw"])
    if not rows:
        return f"<b>🏆 {w('rating', lang)}</b>\n<i>{label(s, e)}</i>\n\n{w('no_data', lang)}"
    medal = ["🥇", "🥈", "🥉"]
    lines = [f"{medal[i] if i < 3 else f'{i + 1}.'} {h(r['p']['name'])} — <b>{num(r['raw'])}</b>"
             for i, r in enumerate(rows)]
    return f"<b>🏆 {w('rating', lang)}</b>\n<i>{label(s, e)}</i>\n\n" + card(lines)


def rating_plain(b: dict, s: dt.date, e: dt.date) -> str:
    """Guruh uchun (/top): faqat kassa summasi, $ va zp yo'q."""
    rows = sorted([r for r in b["rows"].values() if r["raw"] > 0 and r["kind"] in ("worker", "self", "pool")],
                  key=lambda r: -r["raw"])
    if not rows:
        return f"🏆 <b>Рейтинг кассы</b> · {label(s, e)}\n<blockquote>данных нет</blockquote>"
    medal = ["🥇", "🥈", "🥉"]
    return "\n".join([f"🏆 <b>Рейтинг кассы</b> · {label(s, e)}", "<blockquote>" + "\n".join(
        f"{medal[i] if i < 3 else f'{i + 1}.'} {h(r['p']['name'])} — <b>{num(r['raw'])}</b>"
        for i, r in enumerate(rows)) + "</blockquote>"])
