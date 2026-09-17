"""Text utilities for report sanitization and formatting."""
import re

MOJIBAKE_MAP = {
    'Ä…': 'a', 'Ä„': 'A',
    'Ä‡': 'c', 'Ä†': 'C',
    'Ä™': 'e', 'Ä˜': 'E',
    'Å‚': 'l', 'Å ': 'L', 'Å?': 'l',
    'Å„': 'n', 'Åƒ': 'N',
    'Ã³': 'o', 'Ã“': 'O',
    'Å›': 's', 'Åš': 'S',
    'Åº': 'z', 'Å¹': 'Z',
    'Å¼': 'z', 'Å»': 'Z',
    'Ä?': 'e',
    'â€“': '-', 'â€”': '-', 'â€ž': '"', 'â€': '"', 'â€˜': "'", 'â€™': "'",
}

POLISH_ASCII_MAP = {
    'ą': 'a', 'ć': 'c', 'ę': 'e', 'ł': 'l', 'ń': 'n', 'ó': 'o', 'ś': 's', 'ź': 'z', 'ż': 'z',
    'Ą': 'A', 'Ć': 'C', 'Ę': 'E', 'Ł': 'L', 'Ń': 'N', 'Ó': 'O', 'Ś': 'S', 'Ź': 'Z', 'Ż': 'Z',
    '\u2013': '-', '\u2014': '-', '\u2015': '-', '\u2212': '-',
    '\u201c': '"', '\u201d': '"', '\u201e': '"', '\u201f': '"',
    '”': '"', '„': '"', '’': "'", '‘': "'", '‚': "'", '«': '"', '»': '"',
    '…': '...', '\u2026': '...',
    '•': '*', '\u2022': '*',
    '–': '-', '—': '-',
    '\u00a0': ' ', '\u202f': ' ', '\ufeff': ''
}


def format_godziny(wartosc) -> str:
    """Formats numeric hours into h:m display string."""
    if not wartosc:
        return "0h 0m"
    try:
        val = float(wartosc)
        h = int(val)
        m = int(round((val - h) * 60))
        return f"{h}h {m}m"
    except Exception:
        return f"{wartosc}h"


def fix_mojibake(text: str | None) -> str:
    """Repairs double-encoded UTF-8 strings (mojibake)."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""
    for k, v in MOJIBAKE_MAP.items():
        if k in text:
            text = text.replace(k, v)
    return text


def polskie_znaki_pdf(text: str | None) -> str:
    """Sanitizes Polish diacritics, mojibake and emojis for FPDF."""
    if text is None:
        return ""
    text = str(text)
    if not text:
        return ""

    text = fix_mojibake(text)
    for k, v in POLISH_ASCII_MAP.items():
        if k in text:
            text = text.replace(k, v)

    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    text = re.sub(r'[\u2600-\u27bf]', '', text)
    return text.encode('latin-1', 'replace').decode('latin-1')
