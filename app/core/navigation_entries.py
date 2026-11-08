"""Extra switches for menu entries governed by existing module policies."""

# (exact endpoints, route prefixes). Existing endpoint guards remain in force.
ENTRY_ROUTES = {
    'split': ((), ('/magazyn-dostawy/podzial-palety', '/magazyn-dostawy/api/podzial-palety')),
    'mix': ((), ('/magazyn-dostawy/mixowanie', '/magazyn-dostawy/api/mixowanie')),
    'consumption': (('warehouse_v2.zuzycie_view', 'warehouse_v2.api_zuzycie_lookup',
                     'warehouse_v2.api_zuzycie_confirm', 'warehouse_v2.api_zuzycie_history'), ()),
    'orders': (('warehouse_v2.zamowienia', 'warehouse_v2.zamowienie_nowe'),
               ('/warehouse-v2/api/orders',)),
    'dispatch': (('warehouse_v2.zaladunki_view', 'warehouse_v2.api_lookup_pallet',
                  'warehouse_v2.api_dispatch_vehicle', 'warehouse_v2.api_dispatch_history'), ()),
    'transfers': (('warehouse_v2.transfers_osip_view',), ('/osip/transfers', '/osip/api/transfers')),
    'osip_layout': (('osip.warehouse_view', 'osip.get_inventory_api', 'osip.get_layout_api'), ()),
    'osip_stock': (('osip.suma_surowcow_view',), ()),
    'osip_expedition': ((), ('/osip/expedition', '/osip/api/expedition')),
    'printers': ((), ('/admin/ustawienia/drukarki',)),
    'printer_logs': (('admin.admin_ustawienia_logi_drukowania',), ()),
    'traceability': ((), ('/traceability', '/api/traceability')),
    'pallet_report_agro': (('agro_warehouse.raport_palet', 'agro_warehouse.raport_palet_daily'), ()),
    'pallet_report_psd': (('warehouse_v2.raport_palet',), ()),
    'machines': ((), ('/maszyny',)),
    'magnets': ((), ('/quality/magnet-cleaning',)),
    'separators': ((), ('/quality/separator-cleaning',)),
    'users': (('admin.users_center',), ()),
    'email': ((), ('/admin/ustawienia/poczta', '/admin/api/email')),
    'raw_dictionary': ((), ('/admin/slownik-surowcow',)),
    'page_timing': (('admin.system_performance',), ()),
    'mqtt': ((), ('/admin/master/mqtt',)),
    'process_flow': ((), ('/admin/master/process-flow-3d',)),
    'live_line': ((), ('/zarzad/live-line',)),
    'integrity': ((), ('/admin/master/verify',)),
    'zebra_sim': ((), ('/zebra-sim',)),
    'scanner_sim': (('scanner.scanner_simulator',), ()),
}
ENTRY_KEYS = set(ENTRY_ROUTES) | {
    'osip_reception', 'osip_movements', 'osip_pending',
    'dosing_report_agro', 'dosing_report_psd',
}


def entry_switches(endpoint, path, line):
    for entry, (endpoints, prefixes) in ENTRY_ROUTES.items():
        if endpoint in endpoints or any(path == prefix or path.startswith(prefix + '/') for prefix in prefixes):
            yield entry
    if path == '/raporty/zasypy-dosypki':
        if line != 'psd':
            yield 'dosing_report_agro'
        if line != 'agro':
            yield 'dosing_report_psd'
    if line == 'osip':
        entry = {
            'magazyn_dostawy.reception_view': 'osip_reception',
            'magazyn_dostawy.lista_dostaw': 'osip_movements',
            'magazyn_dostawy.oczekujace': 'osip_pending',
        }.get(endpoint)
        if entry:
            yield entry
        if endpoint == 'warehouse_v2.index':
            yield 'osip_layout'


def report_sections(endpoint, path, line):
    if endpoint in {'agro_warehouse.raport_palet', 'agro_warehouse.raport_palet_daily',
                    'production.zasyp_etapy_podsumowanie'}:
        return ('reports_agro',)
    if endpoint == 'warehouse_v2.raport_palet':
        return ('reports_psd',)
    if path == '/raporty/zasypy-dosypki' or endpoint.startswith('warehouse.podsumowanie_zasypow'):
        if line in {'agro', 'psd'}:
            return ('reports_' + line,)
        if endpoint.startswith('warehouse.podsumowanie_zasypow'):
            return ('reports_psd',)
        return ('reports_agro', 'reports_psd')
    if endpoint in {'magazyn_dostawy.raport', 'zarzad.raporty_okresowe'} or path.startswith('/agro/report/'):
        return ('reports_general',)
    return ()
