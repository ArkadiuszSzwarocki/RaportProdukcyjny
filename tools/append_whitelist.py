#!/usr/bin/env python3
import re,glob,os
whitelist='tools/spelling_whitelist.txt'
pattern=re.compile(r"[A-Za-ząćęłńóśźżĄĆĘŁŃÓŚŹŻ0-9\-]+")
words=set()
for f in glob.glob('templates/**/*.html',recursive=True):
    try:
        s=open(f,encoding='utf-8').read()
    except Exception:
        continue
    for w in pattern.findall(s):
        if re.search(r'[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]',w):
            words.add(w)
existing=set()
if os.path.exists(whitelist):
    try:
        existing=set(x.strip() for x in open(whitelist,encoding='utf-8') if x.strip() and not x.strip().startswith('#'))
    except Exception:
        existing=set()
new=[w for w in sorted(words) if w not in existing]
if new:
    with open(whitelist,'a',encoding='utf-8') as out:
        out.write('\n# Auto-added tokens\n')
        for w in new:
            out.write(w+'\n')
print('Added',len(new),'tokens')
