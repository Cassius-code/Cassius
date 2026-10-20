"""Ko'rinish: mavzu (rasm-panel ranglari), tugma uslubi — har admin o'zi tanlaydi (xuddi telefon fon rasmi kabi).

Tugma uslubi Telegram'ning o'z tugmasida ishlaydi:
  • emoji o'rniga oq belgilar (◆ ✦ ❖ …) — jiddiy, bir xil ko'rinish;
  • lotin harflari qalin (𝗡𝗮𝘇𝗼𝗿𝗮𝘁) — bu oddiy Unicode harflar. Kirill harfli tugma o'zgarmaydi.
Tugma rangi va shriftini Telegram o'zi belgilaydi — bot faqat matnini tanlay oladi.
"""
from __future__ import annotations

import re

DEFAULT_THEME = "graphite"

# emoji → oq belgi (iPhone'da ham emoji bo'lib chiqmaydigan belgilar)
SYMBOL = {
    "🚨": "◆", "💵": "✦", "👥": "❖", "📣": "◈", "📊": "✧", "⚙": "⬩", "🌐": "◎",
    "✅": "✓", "👌": "✓", "✖": "✕", "❌": "✕", "⛔": "⊘", "🚫": "⊘", "➕": "+", "−": "−",
    "🗑": "⌫", "🧹": "⌫", "↩": "↶", "👤": "○", "💸": "¤", "❓": "?", "🔢": "#", "🆔": "№",
    "⏳": "◷", "⌛": "◷", "⏱": "◷", "⏰": "◷", "🕘": "◷", "🕒": "◷",
    "🧮": "∑", "✏": "✎", "✍": "✎", "🧾": "≡", "📜": "≡", "📋": "≡", "📄": "▤",
    "🔄": "↻", "🔁": "↻", "♻": "↻", "🔀": "⇆",
    "🔒": "▣", "🔐": "▣", "🔓": "□", "🔑": "⌘",
    "🗓": "▦", "📅": "▦", "📆": "▦",
    "💰": "$", "💲": "$", "💳": "$", "💼": "$",
    "👮": "♛", "👑": "♛",
    "📁": "▭", "🗄": "▭", "📦": "▭",
    "🏆": "★", "🏅": "★", "💯": "★",
    "🙋": "◐", "☕": "◔", "✈": "◑", "🛌": "◑",
    "⏹": "■", "▶": "▸", "⏯": "▸", "⏸": "‖",
    "📲": "↓", "📥": "↓", "💾": "↓", "📤": "↑", "📨": "↑",
    "🎬": "▷", "🎞": "▷", "🎤": "▷", "🎵": "▷", "📎": "▷",
    "🤝": "⇄", "🟢": "●", "⚪": "○", "⭕": "○", "🔴": "◌", "🟡": "◐",
    "⚡": "ϟ", "🔎": "⌕", "🔍": "⌕", "📌": "▪", "🆕": "✱", "👀": "◉", "👁": "◉",
    "🚪": "⇥", "🛠": "✲", "♾": "∞", "🎁": "✚", "🏷": "◇", "▫": "·", "🌅": "◓", "☀": "☼", "🌙": "☾",
    "🚀": "➤", "🔥": "✷", "🔔": "◦", "🛟": "⊕", "📈": "△", "📐": "∠", "🔗": "⊶", "⚠": "△", "🧪": "◇",
    "💬": "·", "🙏": "·", "😊": "·", "🙈": "·", "🎨": "◑", "🔤": "A", "🖼": "▢",
}
_EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿⌀-⏿←-⇿■-◿]")
_VS = re.compile("[️︎‍\U0001F3FB-\U0001F3FF]")
_CYR = re.compile("[Ѐ-ӿ]")
_SAFE = set("◆✦❖◈✧⬩◎✓✕⊘↶○¤◷∑✎≡▤↻⇆▣□⌘▦$♛▭★◐◔◑■▸‖↓↑▷⇄●◌ϟ⌕▪✱◉⇥✲∞✚◇·◓☼☾➤✷◦⊕△∠⊶⌫#№+−⌂•→≈⌀‹›«»▢")


def symbols(s: str) -> str:
    """Emoji → oq belgi. Noma'lum emoji → «◇»."""
    s = _VS.sub("", s)
    out = []
    for ch in s:
        if ch in SYMBOL:
            out.append(SYMBOL[ch])
        elif ch in _SAFE or not _EMOJI.match(ch):
            out.append(ch)
        else:
            out.append("◇")
    return "".join(out)


def bold(s: str) -> str:
    """Lotin harflari va raqamlar — qalin (Unicode). Kirill bo'lsa — o'zgarmaydi (aralash ko'rinmasin)."""
    if _CYR.search(s):
        return s
    out = []
    for ch in s:
        if "A" <= ch <= "Z":
            out.append(chr(0x1D5D4 + ord(ch) - 65))
        elif "a" <= ch <= "z":
            out.append(chr(0x1D5EE + ord(ch) - 97))
        elif "0" <= ch <= "9":
            out.append(chr(0x1D7EC + ord(ch) - 48))
        else:
            out.append(ch)
    return "".join(out)


def label(s: str) -> str:
    return bold(symbols(s))


def style_markup(markup):
    """Panel tugmalarini uslubga keltirish (callback_data o'zgarmaydi)."""
    rows = getattr(markup, "inline_keyboard", None)
    if not rows:
        return markup
    from aiogram.types import InlineKeyboardMarkup
    return InlineKeyboardMarkup(inline_keyboard=[[b.model_copy(update={"text": label(b.text)}) for b in row]
                                                 for row in rows])


# ───────────────────────── sozlamalar (har admin uchun alohida)
def theme_of(db, uid: int | None) -> str:
    from . import cards
    v = (db.get(f"theme:{uid}") if uid else None) or db.get("theme") or DEFAULT_THEME
    return v if v in cards.THEMES else DEFAULT_THEME


def cards_on(db, uid: int | None) -> bool:
    v = (db.get(f"cards:{uid}") if uid else None) or db.get("cards") or "1"
    return v == "1"


def buttons_on(db, uid: int | None) -> bool:
    v = (db.get(f"btnstyle:{uid}") if uid else None) or db.get("btn_style") or "1"
    return v == "1"
