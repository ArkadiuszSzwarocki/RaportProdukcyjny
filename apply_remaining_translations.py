#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zastosuj pozostałe tłumaczenia w szablonach"""

import os
import re

replacements = [
    # 500.html
    ('templates/500.html', 
     'Napotkaliśmy błąd podczas przetwarzania Twojego żądania.',
     "{{ _('napotkalismy_blad') }}"),
    ('templates/500.html',
     'Szczegóły błędu zostały zalogowane i przekazane zespołowi technicznemu.',
     "{{ _('szczegoly_zalogowane') }}"),
    
    # dashboard.html
    ('templates/dashboard.html',
     '"Poprzedni dzień"',
     '"{{ _(\'poprzedni_dzien\') }}"'),
    ('templates/dashboard.html',
     '"Następny dzień"',
     '"{{ _(\'nastepny_dzien\') }}"'),
    ('templates/dashboard.html',
     'Wznów zlecenia z wczoraj',
     "{{ _('wznow_zlecenia_z_wczoraj') }}"),
    
    # dashboard_global.html  
    ('templates/dashboard_global.html',
     'Zakończ zmianę i pobierz raporty',
     "{{ _('zakonczy_zmiane_i_pobierz_raporty') }}"),
    ('templates/dashboard_global.html',
     'Wyślij raport mailem',
     "{{ _('wyslij_raport_mailem') }}"),
    ('templates/dashboard_global.html',
     'Zakończ zmianę i Zapisz Raport',
     "{{ _('zakonczy_zmiane_i_zapisz_raport') }}"),
    
    # panels
    ('templates/panels/obecnosci_panel.html',
     'Ostatnie Nieobecności (30 dni)',
     "{{ _('ostatnie_nieobecnosci') }}"),
    ('templates/panels/obecnosci_panel.html',
     'Brak wpisów z ostatnich 30 dni.',
     "{{ _('brak_wpisow') }}"),
    ('templates/panels/planowane_panel.html',
     'Planowane Urlopy (Następne 60 dni)',
     "{{ _('planowane_urlopy') }}"),
    ('templates/panels/planowane_panel.html',
     'Brak planowanych urlopów.',
     "{{ _('brak_planowanych_urlopow') }}"),
    ('templates/panels/wnioski_panel.html',
     'Zatwierdzenia Wniosków',
     "{{ _('zatwierdzenia_wnioskow') }}"),
    ('templates/panels/wnioski_panel.html',
     'Brak oczekujących wniosków lub brak uprawnień.',
     "{{ _('brak_oczekujacych_wnioskow') }}"),
    
    # obsada
    ('templates/panels_full/obsada_full.html',
     'Obsada - pełna strona',
     "{{ _('obsada_pelna_strona') }}"),
    
    # szarza
    ('templates/szarza.html',
     'Nowa Szarża',
     "{{ _('nowa_sarzha') }}"),
    
    # koniec_zlecenie
    ('templates/koniec_zlecenie.html',
     'Czy zgłaszasz uszkodzone worki?',
     "{{ _('czy_zglosisz_uszkodzone_worki') }}"),
    
    # raport_sent
    ('templates/raport_sent.html',
     'KROK 3: Przeciągnij pobrane pliki do okna wiadomości.',
     "{{ _('krok_3_przeciagnij_pliki') }}"),
    
    # zarzad
    ('templates/zarzad.html',
     'Statystyki Pracowników (HR)',
     "{{ _('statystyki_pracownikow_hr') }}"),
    ('templates/zarzad.html',
     'Łącznie',
     "{{ _('lacznie') }}"),
    ('templates/zarzad.html',
     'Dni Pracy',
     "{{ _('dni_pracy') }}"),
    ('templates/zarzad.html',
     'Nadgodziny',
     "{{ _('nadgodziny') }}"),
    
    # wyjasnij
    ('templates/wyjasnij.html',
     'Wyjaśnienie rozbieżności',
     "{{ _('wyjasnienie_rozbieznosci') }}"),
    
    # podsumowanie
    ('templates/podsumowanie_zmiany_global.html',
     'Awarie / Usterki / Nieobecności',
     "{{ _('awarie_usterki_nieobecnosci') }}"),
]

# Zastosuj replacementy
applied = 0
for filepath, old_text, new_text in replacements:
    fullpath = os.path.join('c:\\Users\\arkad\\Documents\\GitHub\\RaportProdukcyjny', filepath)
    if not os.path.exists(fullpath):
        print(f"❌ Plik nie istnieje: {filepath}")
        continue
    
    with open(fullpath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Escape special chars dla regex
    escaped_old = re.escape(old_text)
    
    if escaped_old in content or old_text in content:
        # Użyj prostej zamiany zamiast regex
        new_content = content.replace(old_text, new_text)
        
        if new_content != content:
            with open(fullpath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            applied += 1
            print(f"✓ Zaktualizowano: {filepath}")
        else:
            print(f"⊘ Brak zmian: {filepath}")
    else:
        print(f"⊘ Nie znaleziono: {filepath}")

print(f"\n{'='*50}")
print(f"✓ Zaktualizowano plików: {applied}")
print(f"{'='*50}")
