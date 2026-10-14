from pathlib import Path

from app.blueprints.admin.backups import _is_valid_backup_filename
from app.core.download_security import report_download_filename_allowed


ROOT = Path(__file__).resolve().parents[1]


def test_report_download_filename_allowlist():
    assert report_download_filename_allowed('Raport_AGRO_2026-09-30.pdf')
    assert report_download_filename_allowed('Raport_PSD_2026-09-30.xlsx')

    for bad in (
        'secrets.txt',
        'Raport_AGRO_2026-09-30.txt',
        '../Raport_AGRO_2026-09-30.pdf',
        '..\\Raport_AGRO_2026-09-30.pdf',
        '/etc/passwd',
        '.env',
    ):
        assert not report_download_filename_allowed(bad)


def test_backup_filename_validator_blocks_traversal():
    assert _is_valid_backup_filename('db-backup-20260930-120000.sql')
    assert not _is_valid_backup_filename('../db-backup-20260930-120000.sql')
    assert not _is_valid_backup_filename('..\\db-backup-20260930-120000.sql')
    assert not _is_valid_backup_filename('db-backup-20260930-120000.sql.exe')


def test_browser_print_bridge_guard_loads_before_legacy_footer_scripts():
    layout = (ROOT / 'templates' / 'layout.html').read_text(encoding='utf-8')
    guard_ref = "filename='js/print_bridge_browser_guard.js'"
    footer_ref = "{% include 'includes/_layout_footer_scripts.html' %}"
    assert guard_ref in layout
    assert footer_ref in layout
    assert layout.index(guard_ref) < layout.index(footer_ref)


def test_browser_print_bridge_guard_blocks_cross_origin_raw_zpl():
    source = (ROOT / 'static' / 'js' / 'print_bridge_browser_guard.js').read_text(encoding='utf-8')
    assert 'target.origin === window.location.origin' in source
    assert "path.endsWith('/drukuj-zpl')" in source
    assert 'Promise.reject' in source
