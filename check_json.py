import json

with open('config/translations.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print(f"Total keys: {len(data)}")
print(f"PL translations: {sum(1 for v in data.values() if 'pl' in v)}")
print(f"UK translations: {sum(1 for v in data.values() if 'uk' in v)}")
