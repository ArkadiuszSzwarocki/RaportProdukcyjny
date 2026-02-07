import re, json
from collections import Counter

LOG_PATH = 'logs\app.log'
PATTERN = re.compile(r'Modal-move debug: (\{.*\})')

counter = Counter()
total = 0

with open(LOG_PATH, 'r', encoding='utf-8') as fh:
    for line in fh:
        m = PATTERN.search(line)
        if not m:
            continue
        try:
            obj = json.loads(m.group(1))
        except Exception:
            continue
        if obj.get('moved'):
            total += 1
            counter[obj.get('id', '<noid>')] += 1

print(total)
for k, v in counter.most_common():
    print(f"{k}\t{v}")
