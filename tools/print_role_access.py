#!/usr/bin/env python3
import json
from collections import defaultdict

cfg_path = 'config/role_permissions.json'

with open(cfg_path, 'r', encoding='utf-8') as f:
    perms = json.load(f)

roles = set()
pages = list(perms.keys())
for p, mapping in perms.items():
    if isinstance(mapping, dict):
        for r in mapping.keys():
            roles.add(r)

roles = sorted(roles)

role_map = defaultdict(list)

for p, mapping in perms.items():
    if not isinstance(mapping, dict):
        continue
    for r, v in mapping.items():
        access = bool(v.get('access'))
        readonly = bool(v.get('readonly'))
        role_map[r].append((p, access, readonly))

for r in sorted(role_map.keys()):
    print(f'Role: {r}')
    rows = role_map[r]
    # show pages where access=True first
    allowed = [p for p,a,ro in rows if a]
    denied = [p for p,a,ro in rows if not a]
    print('  Allowed:')
    for p,a,ro in rows:
        if a:
            print(f'    - {p} (readonly={ro})')
    print('  Denied:')
    for p,a,ro in rows:
        if not a:
            print(f'    - {p}')
    print()

print('Summary:')
for r in sorted(role_map.keys()):
    allowed_count = sum(1 for _,a,_ in role_map[r] if a)
    total = len(role_map[r])
    print(f'  {r}: {allowed_count}/{total} pages allowed')
