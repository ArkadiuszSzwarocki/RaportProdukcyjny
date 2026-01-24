import re
from pathlib import Path

readme = Path('README.md').read_text(encoding='utf-8')
white = Path('tools/spelling_whitelist.txt').read_text(encoding='utf-8')

# Extract words (letters, including Polish diacritics)
words = re.findall(r"[\wĄąĆćĘęŁłŃńÓóŚśŻżŹź]+", readme, flags=re.UNICODE)
# Normalize
words_norm = {w.strip().strip('\'"') for w in words if len(w) > 1}
white_words = {w.strip().lower() for w in re.findall(r".+", white) if w.strip() and not w.strip().startswith('#')}

missing = sorted({w for w in words_norm if w.lower() not in white_words and any(ord(ch) > 127 for ch in w)})

print('Missing words (with non-ASCII chars) from whitelist:')
for w in missing:
    print(w)

# Also show some common ASCII tokens not whitelisted
ascii_missing = sorted({w for w in words_norm if w.lower() not in white_words and all(ord(ch) < 128 for ch in w) and w.isalpha() and w.islower()})
print('\nSample lowercase ASCII words missing (first 50):')
for w in ascii_missing[:50]:
    print(w)
