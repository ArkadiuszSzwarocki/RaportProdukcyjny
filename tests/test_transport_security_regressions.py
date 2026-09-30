from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _text(relative_path):
    return (ROOT / relative_path).read_text(encoding='utf-8')


def test_active_print_clients_do_not_disable_tls_verification():
    active_paths = (
        'app/services/print_server.py',
        'app/services/office_print_service.py',
        'app/services/magazyn_dostawy/commands/pallet_print_dispatcher.py',
        'Dockerfile',
    )
    for relative_path in active_paths:
        source = _text(relative_path)
        assert 'verify=False' not in source, f'TLS verification disabled in {relative_path}'
        assert 'disable_warnings' not in source, f'TLS warnings disabled in {relative_path}'

    office = _text('app/services/office_print_service.py')
    assert 'ignore_https_errors=False' in office


def test_operational_printer_docs_and_tools_do_not_embed_site_specific_192_168_addresses():
    sanitized_paths = (
        'README.md',
        'URUCHAMIANIE_SERWEROW.md',
        'printer_server/server.py',
        'scripts/scan_subnet.py',
        'scripts/diagnose_printer.py',
    )
    for relative_path in sanitized_paths:
        source = _text(relative_path)
        assert '192.168.' not in source, f'Site-specific private IP leaked in {relative_path}'
