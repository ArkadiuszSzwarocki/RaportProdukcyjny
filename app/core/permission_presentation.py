"""Human-readable permission names and page grouping, without changing ACL keys."""

PAGE_NAMES = {
    'zasyp': 'Zasyp', 'workowanie': 'Workowanie', 'bufor': 'Bufor',
    'dashboard': 'Panel główny', 'magazyn': 'Magazyn',
    'zasyp_summary': 'Podsumowanie zasypu', 'pallet_report': 'Raport palet',
}
LABELS = {
    'dashboard': 'Panel główny', 'ustawienia': 'Dostęp do administracji',
    'ustawienia.system': 'Ustawienia systemu', 'ustawienia.zespol': 'Zespół i konta',
    'ustawienia.backups': 'Kopie zapasowe', 'ustawienia.errors': 'Błędy systemu',
    'ustawienia.logs': 'Logi systemu', 'magazyn.view': 'Wszystkie magazyny',
    'magazyn.pending': 'Oczekujące przyjęcia', 'magazyn.reception': 'Przyjęcie dostawy',
    'magazyn.return': 'Przesunięcia palet i zwroty', 'magazyn.agro_total': 'Suma surowców AGRO',
    'magazyn.agro_packaging': 'Opakowania AGRO', 'magazyn.card': 'Karta palety',
    'magazyn.inventory': 'Inwentaryzacja', 'magazyn.mom': 'Rozliczenie MOM',
    'raporty.agro_production': 'Raport produkcji AGRO', 'raporty.agro_warehouse': 'Raport magazynu AGRO',
    'raporty.dostawy': 'Raport dostaw', 'raporty.okresowe': 'Raporty okresowe',
    'raporty.performance': 'Wydajność systemu', 'awarie': 'Awarie i usterki',
    'jakosc': 'Kontrola jakości', 'jakosc.index': 'Kontrola jakości', 'jakosc.analysis': 'Analiza jakości',
    'sim.scanner': 'Symulator skanera', 'sim.zebra': 'Symulator drukarki Zebra',
    'moje_godziny': 'Moje godziny', 'planista': 'Panel planisty', 'plan': 'Plan produkcji',
    'struktura': 'Struktura organizacyjna', 'wyniki': 'Wyniki produkcji',
    'baza_danych': 'Baza danych', 'centrum': 'Centrum diagnostyki',
    'leaves.dodaj': 'Dodawanie urlopu', 'leaves.usun': 'Usuwanie urlopu',
    'leaves.view': 'Kalendarz urlopów', 'production.obsada': 'Obsada produkcji',
    'logs': 'Logi systemu', 'errors': 'Błędy systemu', 'performance': 'Wydajność systemu',
    'dosypki': 'Dosypki', 'podsumowanie_zasypow': 'Podsumowanie zasypu',
    'podsumowanie_szarz': 'Podsumowanie szarż',
}


def page_group(key):
    parts = key.split('.', 1)
    if len(parts) == 2 and parts[0] in {'agro', 'psd'}:
        section = parts[1]
        section = {'zasyp_summary': 'zasyp', 'pallet_report': 'workowanie'}.get(section, section)
        return {'id': parts[0] + '.' + section,
                'title': parts[0].upper() + ' · ' + PAGE_NAMES.get(section, section.replace('_', ' '))}
    if key == 'osip.magazyn':
        return {'id': key, 'title': 'Magazyny · OSIP'}
    if key.startswith('magazyn.'):
        return {'id': key, 'title': 'Magazyny · ' + LABELS.get(key, key.split('.')[-1].replace('_', ' '))}
    area = {'ustawienia': 'Administracja', 'raporty': 'Raporty', 'jakosc': 'Jakość',
            'sim': 'Symulatory', 'leaves': 'Urlopy'}.get(parts[0], 'Pozostałe strony')
    return {'id': parts[0] if len(parts) == 2 else 'other', 'title': area}


def permission_metadata(key, functions):
    if not key.startswith('function.'):
        group = page_group(key)
        label = LABELS.get(key)
        if label is None and key.split('.')[0] in {'agro', 'psd'}:
            section = key.split('.')[-1]
            label = 'Dostęp do strony' if section in {'zasyp', 'workowanie', 'bufor', 'dashboard', 'magazyn'} else PAGE_NAMES.get(section, section.replace('_', ' '))
        return {'label': label or key.replace('_', ' ').replace('.', ' · '),
                'kind': 'page', 'groups': [group]}
    endpoint = key.removeprefix('function.')
    blueprint, _, action = endpoint.partition('.')
    label = functions.get(key, {}).get('label') or action.replace('_', ' ').removeprefix('api ')
    if blueprint == 'production':
        from app.core.production_permissions import FIXED_SECTIONS, ORDER_ACTIONS
        if action in FIXED_SECTIONS:
            pages = ['agro.' + FIXED_SECTIONS[action]]
        elif action in {'dodaj_dosypke', 'potwierdz_dosypke', 'anuluj_dosypke'}:
            pages = ['agro.zasyp', 'psd.zasyp']
        elif action in ORDER_ACTIONS:
            pages = [hall + '.' + section for hall in ['agro', 'psd'] for section in ['zasyp', 'workowanie', 'bufor', 'magazyn']]
        elif action in {'zglos_przestoj_page', 'edytuj_przestoj_page', 'usun_przestoj'}:
            pages = [hall + '.' + section for hall in ['agro', 'psd'] for section in ['zasyp', 'workowanie']]
        else:
            pages = ['agro.zasyp']
    elif blueprint == 'warehouse_v2':
        if action == 'api_dispatch_vehicle':
            pages = ['magazyn.wydania']
        elif action.startswith('api_orders_picking'):
            pages = ['magazyn.kompletacja']
        elif action.startswith('api_orders'):
            pages = ['magazyn.zamowienia']
        else:
            pages = ['magazyn.view']
    elif blueprint == 'maluchy':
        pages = ['agro.zasyp']
    else:
        pages = ['other']
    titles = {'magazyn.wydania': 'Magazyny · Załadunki i wydania',
              'magazyn.kompletacja': 'Magazyny · Kompletacja',
              'magazyn.zamowienia': 'Magazyny · Zamówienia'}
    groups = [page_group(page) for page in pages]
    for group in groups:
        group['title'] = titles.get(group['id'], group['title'])
    return {'label': label, 'kind': 'function', 'groups': groups}
