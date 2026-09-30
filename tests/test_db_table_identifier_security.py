import pytest

from app.db_tables import resolve_table_name


def test_known_table_names_resolve_for_psd_and_agro():
    assert resolve_table_name('plan_produkcji', 'PSD') == 'plan_produkcji'
    assert resolve_table_name('plan_produkcji', 'AGRO') == 'plan_produkcji_agro'
    assert resolve_table_name('zasypy', 'AGRO') == 'szarze_agro'
    assert resolve_table_name('magazyn_surowce', 'AGRO') == 'magazyn_surowce'


def test_unknown_table_identifier_is_rejected():
    with pytest.raises(ValueError):
        resolve_table_name('magazyn_surowce; DROP TABLE uzytkownicy', 'PSD')


def test_unknown_line_identifier_is_rejected():
    with pytest.raises(ValueError):
        resolve_table_name('magazyn_surowce', 'AGRO; DROP TABLE x')
