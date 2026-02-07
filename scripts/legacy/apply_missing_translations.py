#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zastosuj brakujące tłumaczenia w szablonach
"""
import os
import re

translations_map = {
    "Wewnętrzny Błąd Serwera": "{{ _('wewnetrzny_blad') }}",
    "Co możesz zrobić:": "{{ _('co_mozesz_zrobic') }}",
    "Wróć": "{{ _('wroc') }}",
    "Opcotwórz PRje": "{{ _('opcotwórz_prje') }}",
    "Zarządzanie Produkcją (Wszystkie Sekcje)": "{{ _('zarzadzanie_produkcja') }}",
    "Brak zleceń w bazie.": "{{ _('brak_zlecen_bazie') }}",
    "Zarządzanie użytkownikami": "{{ _('zarzadzanie_uzytkownikami') }}",
    "Usuń paletę": "{{ _('usun_palete') }}",
    "Brak palet oczekujących na zatwierdzenie.": "{{ _('brak_palet_czekajacych') }}",
    ">Do przyjęcia<": ">{{ _('do_przyjecia') }}<",
    ">Przyjęta<": ">{{ _('przyjeta') }}<",
    ">Zamknięta<": ">{{ _('zamknieta') }}<",
    "Ładowanie…": "{{ _('ladowanie') }}",
    "Podgląd produkcji dziennej (Zasyp / Workowanie)": "{{ _('podglad_produkcji') }}",
    "Dodaj paletę": "{{ _('dodaj_palete') }}",
    "Edytuj Zgłoszenie": "{{ _('edytuj_zgloszenie') }}",
    "Edytuj paletę": "{{ _('edytuj_palete') }}",
    "Jakość — zlecenia": "{{ _('jakosc_zlecenia') }}",
    "Lista zleceń oznaczonych jako jakość (dezynfekcja, dokumentacja laboratorium itp.).": "{{ _('lista_zlecen_jakosc') }}",
    "Dokumenty jakościowe": "{{ _('dokumenty_jakosciowe') }}",
    "Jeśli brak uszkodzonych worków, wpisz": "{{ _('brak_uszkodzonych') }}",
    "Twoje konto nie jest powiązane z rekordem pracownika. Skontaktuj się z administratorem.": "{{ _('konto_nie_powiazane') }}",
    "Typy — przeglądany": "{{ _('typy_przeglądany') }}",
    "Kalendarz godzin (miesiąc)": "{{ _('kalendarz_godzin') }}",
    "Obłożenie Zmiany (450 min)": "{{ _('oblegenie_zmiany') }}",
    "Dodawanie wielu zleceń - Planista": "{{ _('dodawanie_zlecen') }}",
    "Zmiana Zamknięta Pomyślnie!": "{{ _('zmiana_zamknieta') }}",
    "Pliki Excel i PDF powinny pobrać się automatycznie.": "{{ _('pliki_powinny_pobrac') }}",
    'Kliknij "Otwórz Outlooka".': '{{ _("kliknij_otworz_outlooka") }}',
    "Powód": "{{ _('powod') }}",
    "Ilość": "{{ _('ilosc') }}",
    "Zgłoś Problem / Usterkę": "{{ _('zgloszenie_problem') }}",
}

template_dir = 'templates'
replacements_count = 0

for filename in os.listdir(template_dir):
    if not filename.endswith('.html'):
        continue
    
    filepath = os.path.join(template_dir, filename)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = content
    for old, new in translations_map.items():
        if old in new_content:
            new_content = new_content.replace(old, new)
            replacements_count += 1
    
    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"✓ {filename}")

print(f"\n✓ Zastosowano {replacements_count} zamian w szablonach")
