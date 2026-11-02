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
    "no_partner": ("Artur (hamkor) botda belgilanmagan — uning ulushi hisoblanmadi, jarima va bonuslar hech kimga "
                   "yozilmadi. Belgilash: 👥 Xodimlar → Artur (yo'q bo'lsa — ➕ Yangi xodim) → ⚙️ Sozlamalar → "
                   "🏷 Turi → 🤝 Hamkor",
                   "Артур (партнёр) не отмечен в боте — его доля не посчитана, штрафы и бонусы никому не записаны. "
                   "Отметить: 👥 Сотрудники → Артур (если нет — ➕ Новый сотрудник) → ⚙️ Настройки → 🏷 Тип → "
                   "🤝 Партнёр"),
    "no_partner_s": ("Artur hisobga kirmagan", "Артур не учтён"),
    "own_work": ("siz ishlagan", "вы работали"),
    "acct_of": ("akkauntida", "на аккаунте"), "stood_in": ("o'rniga ishlagan — unga o'tdi",
                                                         "работал(а) вместо — перешло ему"),
    "acct_s": ("akk", "акк."), "delay_w": ("zaderjka", "задержка"), "late_w": ("kech qolish", "опоздание"),
    "advs_pl": ("avans", "аванс"), "zp_total": ("Zp jami", "Зп всего"),
    "moved_to": ("o'rniga ishlagan {}ga o'tdi — bu yerda hisobga kirmaydi:",
                 "перешло {} (работал(а) вместо) — здесь не считается:"),
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
def adj_item(x: dict, kind: str, lang: str, html: bool = True, word: bool = False) -> str:
    """Bitta jarima/bonus/avans — qisqa (egasi, 2026-11-02: ortiqcha gap kerak emas): «29.10 — zaderjka 10 $ · RD 3»,
    «28.10 — 5 $ · Adam akk · RD 3» (o'rniga ishlagan), «31.10 — 7 $ · yaxshi ishladi» (qo'lda yozilgan izoh).
    Guruh buyrug'i matni («@adam бонус 5») va avtomatik izohlar ko'rsatilmaydi."""
    esc = h if html else str
    src = x["source"]
    what = ""
    if kind == "fine" and src in ("delay", "remind"):
        what = w("delay_w", lang)
    elif kind == "fine" and src == "late":
        what = w("late_w", lang)
    elif word:
        what = w(kind, lang)
    bits = [f"{dshort(x['day'])} — {what + ' ' if what else ''}{money(x['usd'])} $"]
    if x.get("via_name"):
        bits.append(f"{esc(x['via_name'])} {w('acct_s', lang)}" + (f" · {esc(x['via_rd'])}" if x.get("via_rd") else ""))
    elif x.get("rd"):
        bits.append(esc(x["rd"]))
    if src in ("manual", "import") and x["note"]:
        bits.append(esc(x["note"][:30]))
    return " · ".join(bits)


ADJ_GROUPS = (("bonuses", "+", "bonuses_pl", "bonus"), ("fines", "−", "fines_pl", "fine"), ("advs", "−", "advs_pl", "adv"))


def adj_lines(r: dict, lang: str) -> list[str]:
    """Bonuslar / jarimalar / avans — har biri jami bilan, ostida kunma-kun (qisqa). O'rniga ishlagan kun uchun
    boshqaga o'tganlari — oxirida, hisobga kirmaydi."""
    out = []
    for key, sign, title_w, kind in ADJ_GROUPS:
        items = r[key]
        if not items:
            continue
        tot = r2(sum(x["usd"] for x in items))
        out.append(f"{sign} {w(title_w, lang).capitalize()}: <b>{money(tot)} $</b>")
        out += [f"   {adj_item(x, kind, lang)}" for x in items]
    moved = r.get("moved", [])
    if moved:
        to = ", ".join(sorted({h(x["to_name"]) for x in moved}))
        out.append(f"<i>↪ {w('moved_to', lang).format(to)}</i>")
        out += [f"   <i>{adj_item(dict(x, via_name=None), x['kind'], lang, word=True)}</i>" for x in moved]
    return out


def total_formula(r: dict, lang: str) -> str:
    """«= 48.79 + 116 − 15 − 20 = 129.79 $» — zp, bonus, jarima, avans (va o'tkazma/ulush) qanchadan qancha."""
    parts = [money(r["zp"])]
    for v, sign in ((r["bonus"], "+"), (r["fine"], "−"), (r["adv"], "−"), (r["tr_in"], "+"), (r["tr_out"], "−"),
                    (r["sin_sum"], "+"), (r["sout_sum"], "−")):
        if v:
            parts.append(f"{sign} {money(v)}")
    head = f"{' '.join(parts)} = " if len(parts) > 1 else ""
    return f"= {head}<b>{money(r['total'])} $</b>"


def zp_part_lines(r: dict, lang: str, html: bool = True) -> list[str]:
    """Bir nechta RD/akkauntdan zp bo'lsa — har biri alohida (foizsiz, kassa $ siz): «  RD 1 · Bayzed akk — 186 $»."""
    parts = r.get("zp_parts") or []
    if len(parts) < 2:
        return []
    esc = h if html else str
    me, out = r["p"]["id"], []
    for x in sorted(parts, key=lambda x: x["acct"] != me):
        if x["acct"] == me:
            where = esc(x["rd"]) if x["rd"] else w("own", lang)
        else:
            nm = f"{esc(x['name'])} {w('acct_s', lang)}"
            where = f"{esc(x['rd'])} · {nm}" if x["rd"] else nm
        out.append(f"  {where} — {money(x['zp'])} $")
    return out


def acct_label(b: dict, acct: int, me: int, lang: str) -> str:
    """Zp qaysi akkaunt/papkadan: o'zinikida — «RD 3»; boshqanikida — «RD 1 · Bayzed akk»."""
    rd = b.get("rds", {}).get(acct, "")
    if acct == me:
        return h(rd) if rd else w("own", lang)
    nm = f"{h(b['names'].get(acct, '?'))} {w('acct_s', lang)}"
    return f"{h(rd)} · {nm}" if rd else nm


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
    elif r["zp_on"]:                                   # har RD (akkaunt) bo'yicha, o'zinikidan boshlab
        me = r["p"]["id"]
        earn = sorted(r["earn"].items(), key=lambda kv: kv[0][0] != me)
        for (acct, p), u in earn:
            out.append(f"{acct_label(b, acct, me, lang)}: {money(u)} $ × {pct(p)} = {money(u * p / 100)} $")
        if len(earn) > 1:
            out.append(f"<b>{w('zp_total', lang)}: {money(r['zp'])} $</b>")
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
        out.append(total_formula(r, lang) if r["kind"] != "partner" else f"= <b>{money(r['total'])} $</b>")
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
        tail = {"uz": f"hafta: {weeks} — «🧮 Haftalik zp» ni bosing",
                "ru": f"неделя: {weeks} — нажмите «🧮 Зп за неделю»"}
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
        rd = b.get("rds", {}).get(r["p"]["id"])
        kl.append(f"{h(r['p']['name'])}{tag}{' · ' + h(rd) if rd else ''} · {kassa_line(r, lang)}{usd}{up}")
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
    """💼 Siz (egasi, 2026-11-02): kassa − Artur (ulushi + jarimalar − bonuslar) − xodimlar zp si (zp + bonuslar −
    jarimalar) = daromadingiz. Akkauntlar bo'yicha — har akkauntdan kimga qancha; siz o'zingiz ishlagan qism alohida."""
    o = b["owner"]
    names = b["names"]
    ptag = f" {pct(o['partner_pct'])}" if o["partner_pct"] is not None else ""
    lines = [f"<b>💼 {w('you', lang)}</b> · <i>{w('only_you', lang)}</i>",
             f"{w('kassa', lang)}: <b>{num(b['raw'])}</b> → {money(o['K'])} $ <i>({w('by_price', lang)})</i>"]
    if o["partner_id"] is None:                     # hamkor yo'q: «Artur 50%: 0 $» deb chalg'itmaymiz
        lines.append(f"⚠️ {w('no_partner', lang)}")
    else:
        lines.append(f"− {w('partner', lang)}{ptag}: {money(o['partner_share'])}"
                     + (f" + {w('fines_pl', lang)} {money(o['pf'])}" if o["pf"] else "")
                     + (f" − {w('bonuses_pl', lang)} {money(o['pb'])}" if o["pb"] else "")
                     + f" = <b>{money(o['partner_share'] + o['pf'] - o['pb'])} $</b>")
        if o["partner_paid"]:
            lines.append(f"− {w('pshares', lang)}: {money(o['partner_paid'])} $")
    lines.append(f"− {w('zps', lang)}: {money(o['zps'])}"
                 + (f" + {w('bonuses_pl', lang)} {money(o['wb'])}" if o["wb"] else "")
                 + (f" − {w('fines_pl', lang)} {money(o['wf'])}" if o["wf"] else "")
                 + f" = <b>{money(o['zps_paid'])} $</b>")
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
            parts = [f"{w('partner', lang)} {money(a['artur'] + a['pshare'])}"] if o["partner_id"] is not None else []
            if a["zp"]:
                parts.append(f"{w('zp', lang).lower()} {money(a['zp'])}")
            if a["share"]:
                parts.append(f"{w('share_s', lang)} {money(a['share'])}")
            mine = f"{w('to_you', lang)} <b>{money(a['mine'])} $</b>"
            if a["own"] and not a["self"]:          # shu akkauntda o'zingiz ham ishlagansiz — qanday chiqqani
                mine += (f" <i>({w('own_work', lang)} {money(a['own_usd'])} $ → {money(a['own'])} + "
                         f"{w('share_s', lang)} {money(a['mine'] - a['own'])})</i>")
            parts.append(mine)
            tag = f" ({w('you', lang).lower()})" if a["self"] else ""
            rd = b.get("rds", {}).get(a["pid"])
            lines.append(f"{nm}{tag}{' · ' + h(rd) if rd else ''} · {money(a['usd'])} $ → " + " · ".join(parts))
    return card(lines, expandable=len(lines) > 14)


def balance_lines(b: dict, lang: str) -> list[str]:
    """🧮 Kassa = Artur (jarima/bonus bilan) + xodimlar (zp, bonus, jarima bilan) + ulushlar + sizga — pul to'liq
    taqsimlanganini tekshirish (faqat egaga)."""
    o = b["owner"]
    mine = r2(o["income"] + o["out_self"] - o["in_self"])
    has_p = o["partner_id"] is not None
    art = r2(o["partner_share"] + o["pf"] - o["pb"]) if has_p else 0.0
    shares = r2(o["owner_paid"] + o["partner_paid"])
    tot = r2(art + o["zps_paid"] + shares + mine)
    ru = lang == "ru"
    parts = ([f"{w('partner', lang)} {money(art)}"] if has_p else []) + \
        [f"{'зп' if ru else 'xodimlar'} {money(o['zps_paid'])}"]
    if shares:
        parts.append(f"{w('share_s', lang)} {money(shares)}")
    parts.append(f"{w('to_you', lang)} {money(mine)}")
    issues = [f"⚠️ {w('no_partner_s', lang)}"] if o["partner_id"] is None else []
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


def person_view(b: dict, r: dict, s: dt.date, e: dt.date, lang: str, owner: bool, zp: bool = True,
                no_pct: bool = False) -> str:
    """Xodim kabineti (ega/admin uchun): kassa, cheklar soni (Кол-во рд), $, bonus, jarima va zp. Hafta hali
    🧮 hisoblanmagan bo'lsa ham zp ko'rinadi — «≈ taxminiy» belgisi bilan. Egasining ulushi bu yerda YO'Q."""
    ru = lang == "ru"
    parts = []
    if r["n"]:
        lines = [f"<b>💵 {w('kassa', lang)}</b> · <i>{label(s, e)}</i>",
                 f"{'Касса' if ru else 'Kassa'}: <b>{num(r['raw'])}</b>",
                 f"{'Кол-во рд' if ru else 'Cheklar (Кол-во рд)'}: <b>{r['n']}</b>",
                 f"{'Касса ($)' if ru else 'Kassa ($)'}: <b>{money(r['usd'])} $</b>"]
        if r["noprice"]:
            lines.append(f"⚠️ {r['noprice']} {w('noprice', lang)}")
        if r["unassigned"]:
            lines.append(f"⚠️ {r['unassigned']} {w('unassigned', lang)}")
        names = b["names"]
        for payee, usd in r["paid_out"].items():
            lines.append(f"🔁 {w('worked', lang)}: {h(names.get(payee, '?'))}")
        parts.append(card(lines))
    if no_pct:
        zl = zp_amount_lines(r, lang)
    else:
        zl = zp_lines(b, r, lang, owner, True)
    if zl:
        est = "" if zp else (" · <i>≈ примерно — 🧮 неделя ещё не рассчитана</i>" if ru else
                             " · <i>≈ taxminiy — 🧮 hafta hali hisoblanmagan</i>")
        parts.append(card([f"<b>💰 {w('zp', lang)}</b> · <i>{label(s, e)}</i>{est}"] + zl))
    return "\n".join(parts) if parts else f"<i>{w('no_data', lang)}</i>"


def zp_amount_lines(r: dict, lang: str) -> list[str]:
    """Foizlarsiz (💵 faqat zp ko'radigan admin uchun): zp summasi, bonus, jarima, avans, jami."""
    ru = lang == "ru"
    out = []
    if r["kind"] in ("worker", "self") and r["zp_on"]:
        out.append(f"{'Зп' if ru else 'Zp'}: <b>{money(r['zp'])} $</b>")
    elif r["kind"] == "pool":
        out.append(f"<i>{'общий аккаунт — зп получают те, кто работал' if ru else 'umumiy akkaunt — zp ishlaganlarga'}</i>")
    out += adj_lines(r, lang)
    for o in r["outs"]:
        out.append(f"− {w('transfer_out', lang)} {money(o['amount'])} $ ({dshort(o['day'])})")
    for i in r["ins"]:
        out.append(f"+ {w('transfer_in', lang)} {money(i['amount'])} $ ({dshort(i['day'])})")
    if r["total"] is not None and r["kind"] in ("worker", "self"):
        out.append(total_formula(r, lang))
    return out


# ───────────────────────── xodimga xabar (ruscha): faqat o'z zp si
def worker_message(r: dict, s: dt.date, e: dt.date, extra: str = "") -> str:
    """Xodimga (ruscha, oddiy matn): zp, bonuslar va jarimalar jami bilan, kunma-kun qisqa, oxirida hisob:
    «Итого: 48.79 + 116 − 15 − 20 = 129.79 $». Kassa $ va boshqalarning raqamlari yo'q."""
    lines = [f"💰 Зарплата · {label(s, e)}", ""]
    if r["zp_on"] and r["kind"] in ("worker", "self"):
        lines.append(f"Зп: {money(r['zp'])} $")
        lines += zp_part_lines(r, "ru", html=False)
    for key, sign, title_w, kind in ADJ_GROUPS:
        items = r[key]
        if not items:
            continue
        lines.append(f"{w(title_w, 'ru').capitalize()}: {sign}{money(r2(sum(x['usd'] for x in items)))} $")
        lines += [f"  {adj_item(x, kind, 'ru', html=False)}" for x in items]
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
            lines += ["", "Итого: " + total_formula(r, "ru")[2:].replace("<b>", "").replace("</b>", "")]
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
