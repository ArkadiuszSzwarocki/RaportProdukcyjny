import re

with open(r'a:\GitHub\RaportProdukcyjny\templates\inwentaryzacja\skaner.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

js_lines = lines[342:1612] + ['\n// --- Dodatkowe funkcje --- \n\n'] + lines[1750:2073]
js_content = ''.join(js_lines)

def replace_url_for(m):
    url_call = m.group(0)
    # Znajdź końcówkę endpointu, np. inwentaryzacja.szukaj_lokalizacji -> szukaj_lokalizacji
    match = re.search(r'[\'\"](.*?)[\'\"]', url_call)
    if match:
        endpoint = match.group(1).split('.')[-1]
        return f'window.INVENTORY_CONFIG.url_{endpoint}'
    return url_call

js_content = re.sub(r'\{\{\s*url_for\([^)]+\)\s*\}\}', replace_url_for, js_content)
js_content = re.sub(r'\{\{\s*sesja_id\s*\}\}', 'window.INVENTORY_CONFIG.sesjaId', js_content)

with open(r'a:\GitHub\RaportProdukcyjny\static\js\inwentaryzacja\skaner.js', 'w', encoding='utf-8') as f:
    f.write(js_content)

print('Utworzono skaner.js')
