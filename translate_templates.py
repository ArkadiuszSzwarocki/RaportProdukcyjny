#!/usr/bin/env python3
"""
Szybki skrypt do tłumaczenia szablonów - stosuje mapping tekstów na klucze {{ _('key') }}
"""
import re
import os

# Mapping tekstów polskich -> klucze tłumaczeń (na podstawie subagent analysis)
TRANSLATIONS_MAP = {
    # dashboard.html
    ('Poprzedni dzień', 'aria-label'): 'poprzedni_dzien',
    ('Następny dzień', 'aria-label'): 'nastepny_dzien',
    ('Widok dla', None): 'widok_dla',
    ('Przyjęto', 'label'): 'przyjeto',
    ('Palet', 'label'): 'palet',
    ('szt.', None): 'szt',
    ('Plan', 'label'): 'plan',
    ('Wykonanie', 'label'): 'wykonanie',
    ('% Realizacja', 'label'): 'procent_realizacja',
    ('Przegląd daty', None): 'przeglad_daty',
    ('Dzień', None): 'dzien',
    ('Tydzień', None): 'tydzien',
    ('Miesiąc', None): 'miesiac',
    ('📦 Palety do Zatwierdzenia', None): 'palety_do_zatwierdzenia',
    ('Nr', None): 'nr',
    ('📋 Produkt', None): 'produkt_symbol',
    ('🕒 Dodana', None): 'dodana_symbol',
    ('⏱️ Czas', None): 'czas_symbol',
    ('✅ Akcja', None): 'akcja_symbol',
    ('Zatwierdź', None): 'zatwierdz',
    ('Brak palet oczekujących na zatwierdzenie.', None): 'brak_palet_oczekujacych',
    ('Brak potwierdzone palet.', None): 'brak_potwierdzonych_palet',
}

def translate_file(filepath, translations_map):
    """Przełóż teksty w pliku na klucze tłumaczeń"""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    changes = 0
    
    # Zamiana tekstów na {{ _('key') }}
    for (text,context), key in translations_map.items():
        # Szukaj tekstu poza już istniejącymi {{ _() }}
        pattern = f'(?<!_\\(\')({re.escape(text)})(?!\\'\\))'
        if re.search(pattern, content):
            content = re.sub(pattern, f"{{{{ _('{ key}') }}}}", content)
            changes += 1
    
    # Zapisz jeśli coś się zmieniło
    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, changes
    return False, 0

# Główne szablony do przetłumaczenia
TEMPLATES = [
    'templates/dashboard.html',
    'templates/moje_godziny.html',
    'templates/planista.html',
    'templates/obsada.html',
    'templates/jakosc.html',
]

if __name__ == '__main__':
    base_dir = '/Users/arkad/Documents/GitHub/RaportProdukcyjny'
    
    print("🔄 Tłumaczenie szablonów...")
    for template in TEMPLATES:
        filepath = os.path.join(base_dir, template)
        if os.path.exists(filepath):
            changed, count = translate_file(filepath, TRANSLATIONS_MAP)
            status = "✅" if changed else "⏭️"
            print(f"{status} {template}: {count} zmian")
        else:
            print(f"❌ Nie znaleziono: {template}")
    
    print("\n✅ Gotowe!")
