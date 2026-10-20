"""Premium rasm-kartochkalar (panelning asosiy ekranlari).

Qorong'i «status» fon, oltin (foil) aksentlar, oltin chiziqli ikonkalar, klassik serif sarlavha.
Pillow bilan chiziladi (brauzersiz, tez). Shriftlar: app/fonts (OFL), bo'lmasa tizimdagilari.

Bloklar:
  ("head", title, sub, ok|None, status)
  ("tiles", [(label, value, small, tone, icon, bar)])    tone: None | "bad" | "good"; small «↑12%» — strelka
  ("wide", label, sub, value, icon)                       oltin plastinka (CASH)
  ("rows", title, [(left, right, icon)])                  icon: ikonka nomi yoki emoji, «1» «2» «3» — medal
  ("chips", [(text, ok)])
"""
from __future__ import annotations

import io
import math
import os
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W = 1080
PAD = 60
GAP = 22
SS = 4                                     # ikonkalar uchun supersampling
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [os.path.join(HERE, "fonts"), HERE, "/usr/share/fonts/opentype/inter", "/usr/share/fonts/truetype/google-fonts",
             "/usr/share/fonts/truetype/baskerville", "/usr/share/fonts/truetype/noto",
             "/usr/share/fonts/truetype/dejavu"]
EMOJI_FILE = "NotoColorEmoji.ttf"

H_HEAD, H_TILE, H_WIDE, H_ROW, H_ROWHEAD, H_CHIP = 168, 206, 164, 70, 84, 58


# ───────────────────────── shriftlar
def _font_path(name: str) -> str | None:
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


_cache: dict = {}


def font(name: str, size: int):
    """name: fayl nomi; o'zgaruvchan shrift uchun «Lora-Variable.ttf@Bold»."""
    key = (name, size)
    if key not in _cache:
        fname, _, style = name.partition("@")
        p = _font_path(fname) or _font_path("DejaVuSans-Bold.ttf" if "Bold" in fname else "DejaVuSans.ttf")
        try:
            f = ImageFont.truetype(p, size) if p else ImageFont.load_default(size)
            if style:
                try:
                    f.set_variation_by_name(style)
                except Exception:
                    pass
        except OSError:
            f = ImageFont.load_default(size)
        try:
            f.rd_name = name
        except Exception:
            pass
        _cache[key] = f
    return _cache[key]


_MISSING = "\U0010FFFD"


def _has(f, ch: str) -> bool:
    """Shriftda shu harf bormi (yo'q harf «□» bo'lib chiqmasligi uchun)."""
    if ch.isspace():
        return True
    key = ("has", getattr(f, "rd_name", id(f)), f.size, ch)
    if key not in _cache:
        try:
            a = f.getmask(ch)
            b = f.getmask(_MISSING)
            _cache[key] = not (a.size == b.size and bytes(a) == bytes(b))
        except Exception:
            _cache[key] = True
    return _cache[key]


def _fallback(f):
    name = getattr(f, "rd_name", "")
    for w in ("Black", "ExtraBold", "SemiBold", "Bold", "Medium", "ExtraLight", "Light", "Thin"):
        if w in name:
            return font(f"InterDisplay-{w}.otf", f.size)
    return font("InterDisplay-Regular.otf", f.size)


def _fit(f, s: str):
    """Harf shriftda bo'lmasa — o'sha qalinlikdagi Inter, u ham bo'lmasa DejaVu."""
    if all(_has(f, ch) for ch in s):
        return f
    for g in (_fallback(f), font("DejaVuSans-Bold.ttf" if "Bold" in getattr(f, "rd_name", "") else "DejaVuSans.ttf",
                                 f.size)):
        if all(_has(g, ch) for ch in s):
            return g
    return _fallback(f)


def emoji(ch: str, size: int) -> Image.Image | None:
    key = ("emoji", ch, size)
    if key in _cache:
        return _cache[key]
    p = _font_path(EMOJI_FILE)
    im = None
    if p:
        try:
            f = ImageFont.truetype(p, 109)
            im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((8, 8), ch, font=f, embedded_color=True)
            box = im.getbbox()
            im = im.crop(box) if box else None
            if im is not None:
                k = size / max(im.size)
                im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        except Exception:
            im = None
    _cache[key] = im
    return im


# ───────────────────────── mavzular
GOLD = ((250, 232, 170), (214, 175, 84), (160, 118, 40))                 # yorug' → o'rta → to'q
FOIL = ((176, 132, 52), (246, 226, 152), (196, 152, 64), (250, 236, 176), (168, 122, 40))
SILVER = ((246, 246, 248), (196, 200, 208), (140, 146, 156))
BRONZE = ((240, 190, 140), (196, 132, 80), (140, 86, 44))


@dataclass
class Theme:
    name: str
    bg: tuple                       # gradient (yuqori-chap → pastki-o'ng)
    glows: tuple                    # (rang, x, y, radius, alpha)
    title: str = "NotoSerif-SemiBold.otf"
    label: str = "InterDisplay-Medium.otf"
    num: str = "InterDisplay-Light.otf"
    text: str = "InterDisplay-Regular.otf"
    numw: str = "InterDisplay-Medium.otf"   # qatorlardagi raqamlar
    tile: tuple = (255, 255, 255, 9)
    border: tuple = (214, 175, 84, 58)
    gold: tuple = GOLD
    foil: tuple = FOIL
    on_foil: tuple = (34, 24, 8)
    muted: tuple = (205, 192, 166)
    fg: tuple = (246, 242, 234)             # asosiy matn
    chip: tuple = (0, 0, 0, 85)             # tugmacha/status foni
    bad: tuple = (236, 120, 108)
    good: tuple = (126, 206, 150)
    icons: str = "line"             # "line" — oltin chiziqli, "emoji" — rangli
    tracking: int = 10
    frame: bool = True
    extra: dict = field(default_factory=dict)


PLAT = ((250, 250, 252), (200, 204, 212), (128, 134, 146))
PLAT_FOIL = ((146, 152, 162), (242, 244, 248), (172, 178, 188), (252, 252, 254), (136, 142, 152))
ROSE = ((252, 220, 206), (222, 160, 140), (156, 96, 80))
ROSE_FOIL = ((178, 108, 90), (250, 216, 200), (200, 134, 114), (253, 226, 212), (166, 98, 82))
INK = ((206, 160, 70), (170, 126, 46), (120, 86, 24))


def _t(name, bg, glow2, **kw):
    """Qorong'i mavzu: tepada oltin nur, pastda o'z rangidagi nur."""
    return Theme(name, bg, (((214, 175, 84), 0.92, 0.0, 450, 40), (glow2, 0.04, 0.96, 480, 60)), **kw)


THEMES = {
    "black": _t("Black Gold", ((6, 6, 8), (20, 17, 13), (5, 5, 6)), (120, 86, 30)),
    "navy": _t("Royal Navy", ((4, 9, 22), (12, 22, 46), (3, 7, 18)), (40, 70, 140),
               title="Lora-Variable.ttf@Bold", tracking=6),
    "emerald": _t("Emerald", ((2, 14, 11), (8, 34, 27), (2, 10, 8)), (20, 110, 80),
                  title="InterDisplay-Light.otf", num="InterDisplay-ExtraLight.otf", tracking=16),
    "bordo": _t("Bordo", ((14, 3, 6), (36, 8, 16), (10, 2, 5)), (130, 20, 40),
                title="FreeSerifBold.ttf", tracking=7),
    "amethyst": _t("Amethyst", ((10, 5, 20), (30, 14, 54), (7, 3, 14)), (100, 50, 170),
                   title="Lora-Variable.ttf@Bold", tracking=6),
    "mocha": _t("Mocha", ((14, 9, 5), (40, 26, 14), (10, 7, 4)), (140, 90, 40)),
    "graphite": Theme("Platinum", ((12, 12, 14), (34, 35, 40), (9, 9, 11)),
                      (((220, 224, 232), 0.92, 0.0, 450, 30), ((90, 96, 110), 0.04, 0.96, 480, 60)),
                      gold=PLAT, foil=PLAT_FOIL, on_foil=(24, 26, 30), border=(200, 204, 212, 60),
                      muted=(190, 194, 204), title="InterDisplay-Light.otf", tracking=16),
    "rose": Theme("Rose Gold", ((10, 7, 8), (30, 20, 22), (8, 5, 6)),
                  (((222, 160, 140), 0.92, 0.0, 450, 40), ((120, 60, 60), 0.04, 0.96, 480, 50)),
                  gold=ROSE, foil=ROSE_FOIL, on_foil=(52, 24, 18), border=(222, 160, 140, 64),
                  muted=(214, 190, 182), title="Lora-Variable.ttf@Bold", tracking=6),
    "ivory": Theme("Ivory", ((252, 248, 238), (240, 230, 208), (250, 244, 230)),
                   (((214, 175, 84), 0.92, 0.0, 450, 50), ((255, 255, 255), 0.04, 0.96, 480, 90)),
                   gold=INK, fg=(34, 28, 18), muted=(118, 102, 76), tile=(255, 255, 255, 120),
                   border=(176, 132, 52, 90), chip=(255, 255, 255, 150), bad=(196, 64, 52), good=(38, 140, 80)),
    "aurora": Theme("Aurora", ((43, 15, 99), (19, 48, 138), (8, 92, 106)),
                    (((168, 85, 247), 0.1, 0.05, 480, 110), ((34, 211, 238), 0.95, 0.9, 520, 110)),
                    gold=((255, 255, 255), (236, 240, 255), (206, 216, 246)),
                    foil=((22, 163, 74), (34, 197, 94), (20, 184, 166), (45, 212, 191)), on_foil=(255, 255, 255),
                    border=(255, 255, 255, 50), tile=(255, 255, 255, 24), muted=(220, 226, 255),
                    title="Poppins-Bold.ttf", tracking=6, frame=False),
}
DEFAULT = "graphite"


# ───────────────────────── chizish yordamchilari
def _lerp(a, b, t):
    return tuple(round(a[j] + (b[j] - a[j]) * t) for j in range(3))


def _stops(stops, t):
    n = len(stops) - 1
    i = min(n - 1, int(t * n))
    return _lerp(stops[i], stops[i + 1], t * n - i)


def _gradient(w: int, h: int, cols: tuple) -> Image.Image:
    small = Image.new("RGB", (64, 64))
    px = small.load()
    for y in range(64):
        for x in range(64):
            px[x, y] = _stops(cols, (x + y) / 126)
    return small.resize((w, h), Image.BICUBIC).convert("RGBA")


def _fill(mask: Image.Image, stops, vertical: bool = True) -> Image.Image:
    """Niqobni metall gradient bilan bo'yash."""
    w, h = mask.size
    n = h if vertical else w
    strip = Image.new("RGB", (1, n) if vertical else (n, 1))
    for i in range(n):
        strip.putpixel((0, i) if vertical else (i, 0), _stops(stops, i / max(1, n - 1)))
    g = strip.resize((w, h)).convert("RGBA")
    g.putalpha(mask)
    return g


def _glow(im: Image.Image, col, x: float, y: float, r: int, a: int) -> None:
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    cx, cy = x * im.width, y * im.height
    ImageDraw.Draw(layer).ellipse((cx - r, cy - r, cx + r, cy + r), fill=col + (a,))
    im.alpha_composite(layer.filter(ImageFilter.GaussianBlur(r * 0.6)))


def _rr(im: Image.Image, box, radius: int, fill=None, outline=None, width: int = 2) -> None:
    """Shaffof to'rtburchak — faqat o'z joyida chiziladi (butun rasm emas: tezroq)."""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    if x1 < x0 or y1 < y0:
        return
    layer = Image.new("RGBA", (x1 - x0 + 1, y1 - y0 + 1), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, x1 - x0, y1 - y0), radius, fill=fill, outline=outline, width=width)
    im.alpha_composite(layer, (x0, y0))


def _foil_rr(im: Image.Image, box, radius: int, stops) -> None:
    x0, y0, x1, y1 = [int(v) for v in box]
    mask = Image.new("L", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, mask.width - 1, mask.height - 1), radius, fill=255)
    g = _fill(mask, stops, vertical=False)
    # yaltiroq: yuqori yarmiga oq shu'la
    sheen = Image.new("L", mask.size, 0)
    ImageDraw.Draw(sheen).rounded_rectangle((0, 0, mask.width - 1, mask.height // 2), radius, fill=38)
    white = Image.new("RGBA", mask.size, (255, 255, 255, 0))
    white.putalpha(Image.composite(sheen, Image.new("L", mask.size, 0), mask))
    g.alpha_composite(white)
    im.alpha_composite(g, (x0, y0))


def _width(s: str, f, tracking: int = 0) -> int:
    f = _fit(f, s)
    d = ImageDraw.Draw(Image.new("L", (1, 1)))
    if not tracking:
        return int(d.textlength(s, font=f))
    return int(sum(d.textlength(ch, font=f) for ch in s) + tracking * (len(s) - 1))


def _text(d: ImageDraw.ImageDraw, xy, s: str, f, fill, tracking: int = 0, anchor: str = "la") -> int:
    """Harflar orasi (tracking) bilan. -> matn kengligi."""
    f = _fit(f, s)
    if not tracking:
        d.text(xy, s, font=f, fill=fill, anchor=anchor)
        return int(d.textlength(s, font=f))
    widths = [d.textlength(ch, font=f) for ch in s]
    total = int(sum(widths) + tracking * (len(s) - 1))
    x, y = xy
    if anchor[0] == "r":
        x -= total
    elif anchor[0] == "m":
        x -= total // 2
    for ch, w in zip(s, widths):
        d.text((x, y), ch, font=f, fill=fill, anchor="l" + anchor[1])
        x += w + tracking
    return total


def _fitf(s: str, name: str, size: int, maxw: int, tracking: int = 0, min_size: int = 18):
    """Matn joyga sig'guncha shriftni kichraytirish."""
    while size > min_size and _width(s, font(name, size), tracking) > maxw:
        size -= 2
    return font(name, size)


def _clip(s: str, f, maxw: int, tracking: int = 0) -> str:
    """Sig'masa — oxiri «…»."""
    if _width(s, f, tracking) <= maxw:
        return s
    while s and _width(s + "…", f, tracking) > maxw:
        s = s[:-1]
    return s.rstrip() + "…"


def _gold_text(im: Image.Image, xy, s: str, f, stops, tracking: int = 0, anchor: str = "la") -> int:
    """Metall (oltin) gradientli matn (faqat matn atrofidagi tasma chiziladi)."""
    top = max(0, int(xy[1] - f.size * 1.2))
    band = Image.new("L", (im.width, int(f.size * 2.6)), 0)
    w = _text(ImageDraw.Draw(band), (xy[0], xy[1] - top), s, f, 255, tracking, anchor)
    box = band.getbbox()
    if box:
        part = band.crop(box)
        im.alpha_composite(_fill(part, stops), (box[0], box[1] + top))
    return w


# ───────────────────────── ikonkalar (oltin chiziq)
class _Pen:
    def __init__(self, size: int):
        self.s = size * SS
        self.m = Image.new("L", (self.s, self.s), 0)
        self.d = ImageDraw.Draw(self.m)
        self.w = max(2, round(self.s * 0.075))

    def p(self, x, y):
        return (x * self.s, y * self.s)

    def line(self, *pts, closed=False):
        pts = [self.p(*q) for q in pts]
        if closed:
            pts = pts + [pts[0], pts[1]]
        self.d.line(pts, fill=255, width=self.w, joint="curve")
        if not closed:
            r = self.w / 2
            for x, y in (pts[0], pts[-1]):
                self.d.ellipse((x - r, y - r, x + r, y + r), fill=255)

    def circle(self, cx, cy, r, fill=False):
        b = (self.p(cx - r, cy - r), self.p(cx + r, cy + r))
        if fill:
            self.d.ellipse(b, fill=255)
        else:
            self.d.ellipse(b, outline=255, width=self.w)

    def arc(self, x0, y0, x1, y1, a0, a1):
        self.d.arc((self.p(x0, y0), self.p(x1, y1)), a0, a1, fill=255, width=self.w)

    def rr(self, x0, y0, x1, y1, r):
        self.d.rounded_rectangle((self.p(x0, y0), self.p(x1, y1)), r * self.s, outline=255, width=self.w)

    def glyph(self, ch, cx, cy, k, name="InterDisplay-SemiBold.otf"):
        f = font(name, int(self.s * k))
        self.d.text(self.p(cx, cy), ch, font=f, fill=255, anchor="mm")

    def mask(self, size):
        return self.m.resize((size, size), Image.LANCZOS)


def _ic_timer(p):
    p.circle(.5, .56, .37); p.line((.5, .56), (.5, .36)); p.line((.5, .56), (.64, .64))
    p.line((.4, .08), (.6, .08)); p.line((.5, .08), (.5, .18))


def _ic_clock(p):
    p.circle(.5, .5, .42); p.line((.5, .5), (.5, .26)); p.line((.5, .5), (.68, .6))


def _ic_alert(p):
    p.line((.5, .08), (.95, .88), (.05, .88), closed=True); p.line((.5, .38), (.5, .6)); p.circle(.5, .74, .045, True)


def _ic_video(p):
    p.rr(.04, .24, .66, .76, .1); p.line((.66, .44), (.96, .26), (.96, .74), (.66, .56))


def _ic_person(p):
    p.circle(.5, .3, .19); p.arc(.12, .6, .88, 1.3, 180, 360)


def _ic_coin(p):
    p.circle(.5, .5, .42); p.glyph("$", .5, .52, .56)


def _ic_cash(p):
    p.rr(.04, .22, .96, .78, .08); p.circle(.5, .5, .13); p.line((.16, .36), (.2, .36)); p.line((.8, .64), (.84, .64))


def _ic_calendar(p, dots=1):
    p.rr(.08, .16, .92, .92, .1); p.line((.08, .38), (.92, .38)); p.line((.3, .06), (.3, .24)); p.line((.7, .06), (.7, .24))
    xs = [.5] if dots == 1 else [.3, .5, .7]
    for x in xs:
        p.circle(x, .64, .06, True)


def _ic_hourglass(p):
    p.line((.22, .08), (.78, .08)); p.line((.22, .92), (.78, .92))
    p.line((.28, .08), (.5, .5), (.72, .08)); p.line((.28, .92), (.5, .5), (.72, .92))


def _ic_receipt(p):
    p.line((.2, .06), (.8, .06), (.8, .94), (.65, .86), (.5, .94), (.35, .86), (.2, .94), closed=True)
    p.line((.34, .32), (.66, .32)); p.line((.34, .5), (.66, .5)); p.line((.34, .68), (.52, .68))


def _ic_wallet(p):
    p.rr(.06, .24, .94, .88, .1); p.line((.6, .48), (.94, .48), (.94, .66), (.6, .66), closed=True)
    p.line((.16, .24), (.7, .08), (.76, .24))


def _ic_sunrise(p):
    p.arc(.24, .44, .76, .96, 180, 360); p.line((.04, .7), (.96, .7))
    p.line((.5, .1), (.5, .24)); p.line((.16, .3), (.24, .38)); p.line((.84, .3), (.76, .38))


def _ic_sun(p):
    p.circle(.5, .5, .2)
    for k in range(8):
        a = k * math.pi / 4
        p.line((.5 + .32 * math.cos(a), .5 + .32 * math.sin(a)), (.5 + .44 * math.cos(a), .5 + .44 * math.sin(a)))


def _ic_moon(p):
    p.circle(.48, .52, .4, True)
    r = .36
    p.d.ellipse((p.p(.66 - r, .36 - r), p.p(.66 + r, .36 + r)), fill=0)


def _ic_pause(p):
    p.circle(.5, .5, .42); p.line((.41, .34), (.41, .66)); p.line((.59, .34), (.59, .66))


def _ic_send(p):
    p.line((.06, .46), (.94, .08), (.62, .92), (.46, .6), closed=True); p.line((.46, .6), (.94, .08))


def _ic_folder(p):
    p.line((.06, .18), (.38, .18), (.48, .3), (.94, .3), (.94, .86), (.06, .86), closed=True)


def _ic_trophy(p):
    p.line((.26, .1), (.74, .1)); p.arc(.26, -.24, .74, .62, 0, 180)
    p.arc(.08, .12, .32, .4, 90, 270); p.arc(.68, .12, .92, .4, 270, 450)
    p.line((.5, .62), (.5, .78)); p.line((.32, .88), (.68, .88)); p.line((.38, .78), (.62, .78))


def _ic_shield(p):
    p.line((.5, .06), (.88, .2), (.84, .56), (.5, .94), (.16, .56), (.12, .2), closed=True)
    p.line((.34, .5), (.46, .62), (.68, .38))


def _ic_percent(p):
    p.circle(.28, .28, .12); p.circle(.72, .72, .12); p.line((.8, .16), (.2, .84))


def _ic_check(p):
    p.circle(.5, .5, .42); p.line((.3, .52), (.44, .66), (.72, .36))


def _ic_question(p):
    p.circle(.5, .5, .42); p.glyph("?", .5, .53, .56)


def _ic_lock(p):
    p.rr(.18, .44, .82, .92, .08); p.arc(.3, .1, .7, .7, 180, 360); p.line((.3, .4), (.3, .44)); p.line((.7, .4), (.7, .44))
    p.circle(.5, .66, .06, True)


def _ic_gift(p):
    p.rr(.12, .4, .88, .92, .06); p.line((.06, .28), (.94, .28), (.94, .4), (.06, .4), closed=True)
    p.line((.5, .28), (.5, .92)); p.arc(.24, .06, .5, .32, 180, 360); p.arc(.5, .06, .76, .32, 180, 360)


def _ic_handshake(p):
    p.line((.04, .36), (.24, .36), (.5, .62), (.62, .62)); p.line((.96, .36), (.76, .36), (.5, .62))
    p.line((.24, .36), (.42, .24), (.6, .3)); p.line((.4, .52), (.52, .44))


ICONS = {"timer": _ic_timer, "clock": _ic_clock, "alert": _ic_alert, "video": _ic_video, "person": _ic_person,
         "coin": _ic_coin, "cash": _ic_cash, "calendar": _ic_calendar, "week": lambda p: _ic_calendar(p, 3),
         "hourglass": _ic_hourglass, "receipt": _ic_receipt, "wallet": _ic_wallet, "sunrise": _ic_sunrise,
         "sun": _ic_sun, "moon": _ic_moon, "pause": _ic_pause, "send": _ic_send, "folder": _ic_folder,
         "trophy": _ic_trophy, "shield": _ic_shield, "percent": _ic_percent, "check": _ic_check,
         "share": _ic_handshake, "question": _ic_question, "lock": _ic_lock,
         "gift": _ic_gift}
EMOJI_ICON = {"⏱": "timer", "🕒": "clock", "🚨": "alert", "🎬": "video", "🙋": "person", "💰": "coin", "💵": "cash",
              "📅": "calendar", "🗓": "week", "⏳": "hourglass", "💸": "receipt", "💳": "wallet", "🌅": "sunrise",
              "☀️": "sun", "🌙": "moon", "🤫": "pause", "🚀": "send", "📁": "folder", "🏆": "trophy",
              "🛡": "shield", "%": "percent", "✅": "check", "🤝": "share", "❓": "question", "🧮": "percent",
              "💼": "wallet", "🕘": "clock", "🔒": "lock", "🔐": "lock", "📲": "send", "👥": "person", "⚙️": "shield",
              "🔑": "lock", "☕": "pause", "⏯": "check", "📣": "send", "📊": "trophy", "🎁": "gift"}


def icon(name: str, size: int, stops=GOLD) -> Image.Image | None:
    key = ("icon", name, size, stops)
    if key in _cache:
        return _cache[key]
    fn = ICONS.get(name)
    im = None
    if fn:
        p = _Pen(size)
        fn(p)
        im = _fill(p.mask(size), stops)
    _cache[key] = im
    return im


def _medal(im: Image.Image, n: str, x: int, y: int, size: int) -> int:
    stops = {"1": GOLD, "2": SILVER, "3": BRONZE}.get(n, GOLD)
    m = Image.new("L", (size * SS, size * SS), 0)
    ImageDraw.Draw(m).ellipse((0, 0, size * SS - 1, size * SS - 1), fill=255)
    disc = _fill(m.resize((size, size), Image.LANCZOS), stops)
    im.alpha_composite(disc, (x, y))
    d = ImageDraw.Draw(im)
    d.text((x + size / 2, y + size / 2 + 1), n, font=font("InterDisplay-Bold.otf", int(size * .56)),
           fill=(40, 28, 10), anchor="mm")
    return size


def _icon_at(im: Image.Image, th: Theme, ic: str | None, x: int, y: int, size: int, stops=None) -> int:
    """Ikonka (nomi yoki emoji) — chizilgan kenglik."""
    if not ic:
        return 0
    if ic in ("1", "2", "3"):
        return _medal(im, ic, x, y, size)
    if th.icons == "line":
        name = EMOJI_ICON.get(ic, ic)
        g = icon(name, size, stops or th.gold)
        if g is not None:
            im.alpha_composite(g, (int(x), int(y)))
            return size
    e = emoji(ic, size)
    if e is None:
        return 0
    im.alpha_composite(e, (int(x), int(y + (size - e.height) / 2)))
    return e.width


# ───────────────────────── ekran
_BG: dict = {}


def _background(key: str, th: Theme, h: int) -> Image.Image:
    """Fon (gradient, nurlar, don, ramka) — mavzu va balandlik bo'yicha keshlanadi."""
    k = (key, h)
    if k not in _BG:
        if len(_BG) > 24:
            _BG.clear()
        im = _gradient(W, h, th.bg)
        small = Image.new("RGBA", (W // 4, h // 4), (0, 0, 0, 0))     # nurlar kichik o'lchamda (tez)
        for col, x, y, r, a in th.glows:
            _glow(small, col, x, y, r // 4, a)
        im.alpha_composite(small.resize((W, h), Image.BICUBIC))
        noise = Image.effect_noise((W, h), 40).convert("L")          # mayda don (matovaya tekstura)
        im.alpha_composite(Image.merge("RGBA", (noise, noise, noise, Image.new("L", (W, h), 7))))
        if th.frame:
            _rr(im, (16, 16, W - 17, h - 17), 34, outline=th.gold[1] + (60,), width=2)
        _BG[k] = im
    return _BG[k].copy()


def render(blocks: list, theme: str = DEFAULT, fmt: str = "JPEG") -> bytes:
    key = theme if theme in THEMES else DEFAULT
    th = THEMES[key]
    h = _measure(blocks)
    im = _background(key, th, h)
    d = ImageDraw.Draw(im)
    y = PAD
    for b in blocks:
        kind = b[0]
        if kind == "head":
            y = _head(im, d, th, y, *b[1:])
        elif kind == "tiles":
            y = _tiles(im, d, th, y, b[1])
        elif kind == "wide":
            y = _wide(im, d, th, y, *b[1:])
        elif kind == "rows":
            y = _rows(im, d, th, y, *b[1:])
        elif kind == "chips":
            y = _chips(im, d, th, y, b[1])
        y += GAP
    out = io.BytesIO()
    if fmt == "PNG":
        im.convert("RGB").save(out, "PNG", optimize=True)
    else:
        im.convert("RGB").save(out, "JPEG", quality=90, subsampling=0, optimize=True)
    return out.getvalue()


def _measure(blocks) -> int:
    h = PAD * 2 - GAP
    for b in blocks:
        k = b[0]
        if k == "head":
            h += H_HEAD
        elif k == "tiles":
            h += math.ceil(len(b[1]) / 2) * (H_TILE + GAP) - GAP
        elif k == "wide":
            h += H_WIDE
        elif k == "rows":
            h += H_ROWHEAD + len(b[2]) * H_ROW + 10
        elif k == "chips":
            h += H_CHIP
        h += GAP
    return h


def _head(im, d, th: Theme, y: int, title: str, sub: str, ok: bool | None = None, status: str = "") -> int:
    x = PAD
    # monogramma: oltin romb
    s = 44
    m = Image.new("L", (s * SS, s * SS), 0)
    md = ImageDraw.Draw(m)
    c = s * SS / 2
    md.polygon([(c, 0), (2 * c, c), (c, 2 * c), (0, c)], fill=255)
    md.polygon([(c, 26), (2 * c - 26, c), (c, 2 * c - 26), (26, c)], fill=0)
    md.polygon([(c, 52), (2 * c - 52, c), (c, 2 * c - 52), (52, c)], fill=255)
    im.alpha_composite(_fill(m.resize((s, s), Image.LANCZOS), th.gold), (x, y + 12))
    room = W - PAD - (x + s + 24) - ((_width(status, font(th.label, 24), 4) + 100) if status else 0)
    tf = _fitf(title.upper(), th.title, 58, room, th.tracking, 30)
    _gold_text(im, (x + s + 24, y + 36), _clip(title.upper(), tf, room, th.tracking), tf, th.gold, th.tracking, "lm")
    subf = font(th.text, 31)
    _text(d, (x, y + 112), _clip(sub, subf, W - 2 * PAD, 1), subf, th.muted, 1, "lm")
    # oltin ingichka chiziq (o'ngga qarab so'nadi)
    lw = W - 2 * PAD
    ln = Image.linear_gradient("L").rotate(90, expand=True).resize((lw, 2))
    ln = Image.eval(ln, lambda v: (255 - v) * 170 // 255)
    im.alpha_composite(_fill(ln, th.gold, vertical=False), (PAD, y + H_HEAD - 14))
    if status:
        f = font(th.label, 24)
        tw = _width(status, f, 4)
        pw = tw + 74
        bx = W - PAD - pw
        _rr(im, (bx, y + 10, bx + pw, y + 62), 26, fill=th.chip, outline=th.gold[1] + (120,), width=2)
        col = th.good if ok else th.bad
        _rr(im, (bx + 20, y + 28, bx + 36, y + 44), 8, fill=col + (255,))
        _gold_text(im, (bx + 50, y + 37), status, f, th.gold, 4, "lm")
    return y + H_HEAD


def _delta(im, d, th: Theme, x: int, y: int, s: str) -> None:
    up = s.startswith("↑")
    col = th.good if up else th.bad
    t = s[1:].strip()
    tri = [(x, y + 9), (x + 16, y + 9), (x + 8, y - 5)] if up else [(x, y - 5), (x + 16, y - 5), (x + 8, y + 9)]
    d.polygon(tri, fill=col)
    _text(d, (x + 24, y + 2), t, font(th.label, 30), col, 0, "lm")


def _tiles(im, d, th: Theme, y: int, tiles: list) -> int:
    cw = (W - 2 * PAD - GAP) // 2
    ch = H_TILE
    for i, t in enumerate(tiles):
        label, value, small, tone, ic, bar = (list(t) + [None] * 6)[:6]
        x = PAD + (i % 2) * (cw + GAP)
        yy = y + (i // 2) * (ch + GAP)
        border = th.border if tone != "bad" else th.bad + (110,)
        _rr(im, (x, yy, x + cw, yy + ch), 30, fill=th.tile, outline=border, width=2)
        _rr(im, (x + 2, yy + 2, x + cw - 2, yy + ch // 2), 28, fill=(255, 255, 255, 5))   # shisha shu'lasi
        lx = x + 30
        stops = th.gold if tone != "bad" else (th.bad, th.bad, (190, 80, 70))
        if ic:
            lx += _icon_at(im, th, ic, lx, yy + 26, 38, stops) + 16
        lf = _fitf(label.upper(), th.label, 24, x + cw - 24 - lx, 4, 18)
        _text(d, (lx, yy + 46), _clip(label.upper(), lf, x + cw - 24 - lx, 4), lf, th.muted, 4, "lm")
        vcol = th.bad if tone == "bad" and str(value) not in ("0", "0 $") else th.fg
        sw = (_width(small, font(th.label, 32)) + 40) if small else 0
        vf = _fitf(str(value), th.num, 92, cw - 56 - sw, 0, 40)
        vw = _text(d, (x + 28, yy + 128), str(value), vf, vcol, 0, "lm")
        if small:
            sx = x + 28 + vw + 16
            if small[0] in "↑↓":
                _delta(im, d, th, sx, yy + 140, small)
            else:
                _text(d, (sx, yy + 142), small, font(th.label, 32), th.muted, 0, "lm")
        if bar is not None:
            bx0, bx1, by = x + 30, x + cw - 30, yy + ch - 28
            _rr(im, (bx0, by, bx1, by + 8), 4, fill=(255, 255, 255, 30))
            wfill = max(8, int((bx1 - bx0) * max(0.0, min(1.0, bar))))
            m = Image.new("L", (wfill, 8), 0)
            ImageDraw.Draw(m).rounded_rectangle((0, 0, wfill - 1, 7), 4, fill=255)
            im.alpha_composite(_fill(m, th.gold, vertical=False), (bx0, by))
    return y + math.ceil(len(tiles) / 2) * (ch + GAP) - GAP


def _wide(im, d, th: Theme, y: int, label: str, sub: str, value: str, ic: str | None = None) -> int:
    x0, x1 = PAD, W - PAD
    hh = H_WIDE
    m = 40                                                                          # soya
    sh = Image.new("RGBA", (x1 - x0 + 2 * m, hh + 2 * m), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((m + 10, m + 18, x1 - x0 + m - 10, hh + m + 10), 34, fill=(0, 0, 0, 150))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(16)), (x0 - m, y - m))
    _foil_rr(im, (x0, y, x1, y + hh), 34, th.foil)
    dark = th.on_foil
    lx = x0 + 34
    if ic:
        if th.icons == "line":
            g = icon(EMOJI_ICON.get(ic, ic), 58, (dark, dark, dark))
            if g is not None:
                im.alpha_composite(g, (lx, y + 32))
                lx += 58 + 20
        else:
            lx += _icon_at(im, th, ic, lx, y + 32, 58) + 20
    vf = _fitf(value, "InterDisplay-SemiBold.otf", 84, (x1 - x0) // 2, 0, 44)
    vw = _width(value, vf)
    room = x1 - 36 - vw - 28 - lx
    tf = _fitf(label.upper(), th.title, 44, room, th.tracking, 26)
    _text(d, (lx, y + 62), _clip(label.upper(), tf, room, th.tracking), tf, dark, th.tracking, "lm")
    if sub:
        sf = font(th.text, 27)
        _text(d, (lx, y + 112), _clip(sub, sf, room), sf, dark, 0, "lm")
    _text(d, (x1 - 36, y + hh // 2 + 2), value, vf, dark, 0, "rm")
    return y + hh


def _rows(im, d, th: Theme, y: int, title: str, rows: list) -> int:
    x0, x1 = PAD, W - PAD
    hh = H_ROWHEAD + len(rows) * H_ROW + 10
    _rr(im, (x0, y, x1, y + hh), 30, fill=th.tile, outline=th.border, width=2)
    _text(d, (x0 + 30, y + 46), title.upper(), font(th.label, 24), th.muted, 4, "lm")
    yy = y + H_ROWHEAD
    for k, (left, right, ic) in enumerate(rows):
        if k:
            _rr(im, (x0 + 30, yy - 1, x1 - 30, yy), 0, fill=(255, 255, 255, 16))
        lx = x0 + 30
        if ic:
            lx += _icon_at(im, th, ic, lx, yy + 14, 42) + 20
        rf = _fitf(right, th.numw, 36, (x1 - x0) // 2, 0, 24)
        rw = _width(right, rf)
        lf = font(th.text, 34)
        _text(d, (lx, yy + 36), _clip(left, lf, x1 - 30 - rw - 24 - lx), lf, th.fg, 0, "lm")
        _gold_text(im, (x1 - 30, yy + 36), right, rf, th.gold, 0, "rm")
        yy += H_ROW
    return y + hh


def _chips(im, d, th: Theme, y: int, chips: list) -> int:
    x = PAD
    f = font(th.label, 25)
    for text, ok in chips:
        tw = _width(text, f, 1)
        cw = tw + 70
        if x + cw > W - PAD:
            break
        _rr(im, (x, y, x + cw, y + H_CHIP), 29, fill=th.chip, outline=th.gold[1] + (70,), width=2)
        col = th.good if ok else th.bad
        _rr(im, (x + 22, y + 22, x + 36, y + 36), 7, fill=col + (255,))
        _text(d, (x + 48, y + H_CHIP // 2), text, f, th.muted, 1, "lm")
        x += cw + 14
    return y + H_CHIP
