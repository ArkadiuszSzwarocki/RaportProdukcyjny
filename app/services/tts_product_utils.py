import re
import unicodedata
from typing import Optional


_TTS_TOKEN_REPLACEMENTS = {
    'biala': 'biała',
    'biale': 'białe',
    'bialy': 'biały',
    'maslanka': 'maślanka',
    'poltluste': 'półtłuste',
    'poltlusty': 'półtłusty',
    'smietana': 'śmietana',
    'smietankowe': 'śmietankowe',
    'tluste': 'tłuste',
    'tlusty': 'tłusty',
    'twarog': 'twaróg',
    'zolta': 'żółta',
    'zolte': 'żółte',
    'zolty': 'żółty',
}


def normalize_product_for_tts(produkt: Optional[str]) -> str:
    """Normalize product text so browser/engine TTS pronounces it naturally."""
    text = str(produkt or '').strip()
    if not text:
        return ''

    text = unicodedata.normalize('NFC', text)
    text = re.sub(r'\d+', ' ', text)
    text = text.replace('_', ' ').replace('/', ' ').replace('-', ' ')
    text = text.replace(',', ' ').replace(';', ' ').replace(':', ' ')

    raw_tokens = [t for t in text.split() if t]
    if not raw_tokens:
        return ''

    # Join accidental letter-by-letter tokens like: B I A L E -> BIALE.
    tokens: list[str] = []
    i = 0
    while i < len(raw_tokens):
        if len(raw_tokens[i]) == 1 and raw_tokens[i].isalpha():
            j = i
            seq: list[str] = []
            while j < len(raw_tokens) and len(raw_tokens[j]) == 1 and raw_tokens[j].isalpha():
                seq.append(raw_tokens[j])
                j += 1
            if len(seq) >= 3:
                tokens.append(''.join(seq))
            else:
                tokens.extend(seq)
            i = j
            continue
        tokens.append(raw_tokens[i])
        i += 1

    normalized_tokens: list[str] = []
    for token in tokens:
        lower = token.lower()
        normalized_tokens.append(_TTS_TOKEN_REPLACEMENTS.get(lower, lower))

    out = ' '.join(normalized_tokens)
    out = re.sub(r'\s+', ' ', out).strip()
    if len(out) > 120:
        out = out[:120].strip()
    return out


def should_speak_product_for_szarza(szarza_nr: Optional[int]) -> bool:
    """Speak product/order name only for first batch, as requested by operators."""
    try:
        return int(szarza_nr) == 1
    except Exception:
        return False
