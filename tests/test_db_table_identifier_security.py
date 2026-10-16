import pytest

from app.db_tables import resolve_table_name


def test_known_table_names_resolve_for_psd_and_agro():
    assert resolve_table_name('plan_produkcji', 'PSD') == 'plan_produkcji'
    assert resolve_table_name('plan_produkcji', 'AGRO') == 'plan_produkcji_agro'
    assert resolve_table_name('zasypy', 'AGRO') == 'szarze_agro'
    assert resolve_table_name('magazyn_surowce', 'AGRO') == 'magazyn_surowce'


def test_osip_can_only_use_shared_tables():
    assert resolve_table_name('magazyn_surowce', 'OSIP') == 'magazyn_surowce'
    assert resolve_table_name('magazyn_dodatki', 'OSIP') == 'magazyn_dodatki'
    assert resolve_table_name('magazyn_palety', 'OSIP') == 'magazyn_palety'
    with pytest.raises(ValueError):
        resolve_table_name('plan_produkcji', 'OSIP')


def test_unknown_table_identifier_is_rejected():
    malicious_names = (
        'magazyn_surowce; DROP TABLE uzytkownicy',
        'magazyn_surowce` WHERE 1=1 --',
        '../magazyn_surowce',
        'uzytkownicy',
    )
    for table_name in malicious_names:
        with pytest.raises(ValueError):
            resolve_table_name(table_name, 'PSD')


def test_unknown_line_identifier_is_rejected():
    malicious_lines = (
        'AGRO; DROP TABLE x',
        'PSD OR 1=1',
        '../AGRO',
        'UNKNOWN',
    )
    for line_name in malicious_lines:
        with pytest.raises(ValueError):
            resolve_table_name('magazyn_surowce', line_name)


@pytest.mark.parametrize('line', ['PSD', 'AGRO', 'ALL', 'OSIP'])
def test_shift_notes_keep_the_existing_shared_table(line):
    assert resolve_table_name('shift_notes', line) == 'shift_notes'


def test_shift_notes_do_not_relax_identifier_or_line_validation():
    with pytest.raises(ValueError):
        resolve_table_name('shift_notes; DROP TABLE x', 'AGRO')
    with pytest.raises(ValueError):
        resolve_table_name('shift_notes', "AGRO'; DROP TABLE x; --")
