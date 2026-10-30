"""PDF hisobot (so'ralganda): kassa jadvali, zp formulalari, egasining bo'limi (faqat egaga), kunlar bo'yicha cheklar.
reportlab + DejaVu shrifti (kirill va lotin)."""
from __future__ import annotations

import datetime as dt
import io
import os
import re
import urllib.request
from xml.sax.saxutils import escape

from . import kassa_view as V

FONT_URL = "https://raw.githubusercontent.com/matplotlib/matplotlib/v3.9.2/lib/matplotlib/mpl-data/fonts/ttf/"
_ready = False


def _font(name: str) -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    data = os.environ.get("DATA_DIR", "/data")
    for p in (os.path.join(here, name), os.path.join(data, "fonts", name), "/usr/share/fonts/truetype/dejavu/" + name,
              "/usr/share/fonts/dejavu/" + name):
        if os.path.isfile(p):
            return p
    os.makedirs(os.path.join(data, "fonts"), exist_ok=True)
    dest = os.path.join(data, "fonts", name)
    urllib.request.urlretrieve(FONT_URL + name, dest)
    return dest


def _setup() -> None:
    global _ready
    if _ready:
        return
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    pdfmetrics.registerFont(TTFont("DJ", _font("DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DJB", _font("DejaVuSans-Bold.ttf")))
    _ready = True


def _styles():
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    ink = colors.HexColor("#1F2430")
    return {"h": ParagraphStyle("h", fontName="DJB", fontSize=17, leading=21, textColor=ink),
            "sub": ParagraphStyle("sub", fontName="DJ", fontSize=9, leading=12, textColor=colors.HexColor("#6B7280")),
            "b": ParagraphStyle("b", fontName="DJB", fontSize=11, leading=15, textColor=ink, spaceBefore=8),
            "p": ParagraphStyle("p", fontName="DJ", fontSize=9.5, leading=13, textColor=ink),
            "c": ParagraphStyle("c", fontName="DJ", fontSize=8, leading=10, textColor=ink),
            "cb": ParagraphStyle("cb", fontName="DJB", fontSize=8, leading=10, textColor=colors.white)}


def _plain(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


_KEEP = set("←→↩−–—×≈…·")


def _clean(t: str) -> str:
    """Shriftda yo'q belgilar (emoji) olib tashlanadi."""
    out = "".join(ch for ch in t if ord(ch) < 0x2190 or ch in _KEEP)
    return re.sub(r"\s{2,}", " ", out).strip()


def _p(t, s):
    from reportlab.platypus import Paragraph
    return Paragraph(escape(_clean(str(t))), s)


def _table(rows, widths, head=True):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle
    t = Table(rows, colWidths=widths, repeatRows=1 if head else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D1D5DB")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F8FA")])]
    if head:
        style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F2430")))
    t.setStyle(TableStyle(style))
    return t


def overall_pdf(b: dict, s: dt.date, e: dt.date, lang: str, owner: bool, zp: bool = True) -> bytes:
    _setup()
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Spacer
    st = _styles()
    L = (lambda uz, ru: ru if lang == "ru" else uz)
    rows_all = [b["rows"][i] for i in b["order"] if i in b["rows"]]
    vis = [r for r in rows_all if owner or r["kind"] in ("worker", "pool")]
    story = [_p(L("Kassa hisoboti", "Отчёт по кассе"), st["h"]), _p(V.label(s, e), st["sub"]), Spacer(1, 10)]
    head = [L("Akkaunt", "Аккаунт"), L("Chek", "Чеки"), L("Kassa", "Касса"), "$"]
    data = [[_p(x, st["cb"]) for x in head]]
    tn = traw = 0
    tusd = 0.0
    for r in vis:
        if r["kind"] == "partner" or not r["n"]:
            continue
        data.append([_p(r["p"]["name"] + (L(" (umumiy)", " (общий)") if r["kind"] == "pool" else ""), st["c"]),
                     _p(r["n"], st["c"]), _p(V.num(r["raw"]), st["c"]), _p(V.money(r["usd"]), st["c"])])
        tn, traw, tusd = tn + r["n"], traw + r["raw"], tusd + r["usd"]
    data.append([_p(L("JAMI", "ИТОГО"), st["c"]), _p(tn, st["c"]), _p(V.num(traw), st["c"]), _p(V.money(tusd), st["c"])])
    story.append(_table(data, [200, 60, 120, 100]))
    story += [Spacer(1, 6), _p(L("Zp", "Зп"), st["b"])]
    if not zp:
        story.append(_p(L("Zp hali hisoblanmagan — faqat jarima, bonus, avans.",
                          "Зп ещё не рассчитана — только штрафы, бонусы, авансы."), st["p"]))
    for r in vis:
        if r["kind"] not in ("worker", "self") or not (r["earn"] or r["fines"] or r["bonuses"] or r["advs"] or r["sin"]):
            continue
        lines = V.zp_lines(b, r, lang, owner, zp)
        if not zp and len(lines) <= 1:
            continue
        story.append(_p(r["p"]["name"], st["b"]))
        for line in lines[1:] if not zp else lines:
            story.append(_p(_plain(line), st["p"]))
    if owner and zp:
        story += [Spacer(1, 6)]
        for line in _plain(V.owner_card(b, lang)).split("\n"):
            story.append(_p(line, st["b"] if line.startswith("💼") else st["p"]))
    story += [Spacer(1, 10), _p(L("Kunlar bo'yicha cheklar", "Чеки по дням"), st["b"])]
    for r in vis:
        if not r["n"]:
            continue
        story.append(_p(r["p"]["name"], st["b"]))
        data = [[_p(x, st["cb"]) for x in (L("Kun", "День"), L("Cheklar", "Чеки"), L("Kassa", "Касса"), "$")]]
        for d, dd in r["days"].items():
            data.append([_p(V.dshort(d), st["c"]), _p(", ".join(str(a) for a, _u in dd["items"])
                                                      + (f"  → {', '.join(dd['ops'])}" if dd["ops"] else ""), st["c"]),
                         _p(V.num(dd["raw"]), st["c"]), _p(V.money(dd["usd"]), st["c"])])
        story.append(_table(data, [50, 290, 80, 60]))
    story += [Spacer(1, 12), _p(dt.datetime.now().strftime("%d.%m.%Y %H:%M"), st["sub"])]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=32, rightMargin=32, topMargin=32, bottomMargin=32).build(story)
    return buf.getvalue()


def person_pdf(b: dict, r: dict, s: dt.date, e: dt.date, lang: str, owner: bool, ready: bool = True) -> bytes:
    """📄 Bitta xodim: kassa (cheklar soni, $), kunlar bo'yicha cheklar, bonus/jarima va zp (hisoblanmagan bo'lsa —
    «taxminiy»). Egasining va Arturning ulushi yo'q."""
    _setup()
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Spacer
    st = _styles()

    def L(uz, ru):
        return ru if lang == "ru" else uz
    story = [_p(r["p"]["name"], st["h"]), _p(V.label(s, e), st["sub"]), Spacer(1, 10)]
    head = [L("Cheklar (Кол-во рд)", "Кол-во рд"), L("Kassa", "Касса"), L("Kassa ($)", "Касса ($)")]
    story.append(_table([[_p(x, st["cb"]) for x in head],
                         [_p(r["n"], st["c"]), _p(V.num(r["raw"]), st["c"]), _p(V.money(r["usd"]) + " $", st["c"])]],
                        [160, 160, 160]))
    story += [Spacer(1, 8), _p(L("Zp", "Зп") + ("" if ready else L(" (taxminiy — hafta hali hisoblanmagan)",
                                                                      " (примерно — неделя ещё не рассчитана)")),
                               st["b"])]
    for line in V.zp_lines(b, r, lang, owner, True):
        story.append(_p(_plain(line), st["p"]))
    if r["n"]:
        story += [Spacer(1, 10), _p(L("Kunlar bo'yicha cheklar", "Чеки по дням"), st["b"])]
        data = [[_p(x, st["cb"]) for x in (L("Kun", "День"), L("Cheklar", "Чеки"), L("Kassa", "Касса"), "$")]]
        for d, dd in r["days"].items():
            data.append([_p(V.dshort(d), st["c"]), _p(", ".join(str(a) for a, _u in dd["items"])
                                                      + (f"  → {', '.join(dd['ops'])}" if dd["ops"] else ""), st["c"]),
                         _p(V.num(dd["raw"]), st["c"]), _p(V.money(dd["usd"]), st["c"])])
        story.append(_table(data, [50, 290, 80, 60]))
    story += [Spacer(1, 12), _p(dt.datetime.now().strftime("%d.%m.%Y %H:%M"), st["sub"])]
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=32, rightMargin=32, topMargin=32, bottomMargin=32).build(story)
    return buf.getvalue()
