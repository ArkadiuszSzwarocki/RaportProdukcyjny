import json

# Wszystkie strony z handlera
pages = ['dashboard','ustawienia','jakosc','planista','plan','zasyp','workowanie','magazyn','moje_godziny','awarie','wyniki']

# Wszystkie role z bazy
roles = ['admin', 'planista', 'pracownik', 'magazynier', 'dur', 'zarzad', 'laboratorium']

# Wczytaj istniejący config
with open('config/role_permissions.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# Dla każdej strony - dodaj wszystkie role z access:true
for page in pages:
    if page not in config:
        config[page] = {}
    
    for role in roles:
        if role not in config[page]:
            # Dodaj role z domyślnym access:true
            config[page][role] = {'access': True, 'readonly': False}

# Zapisz
with open('config/role_permissions.json', 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2, ensure_ascii=False)

print(f'✓ Dodano wszystkie {len(roles)} rol do wszystkich {len(pages)} stron')
print(f'\nRole: {", ".join(roles)}')
print(f'Strony: {", ".join(pages)}')
