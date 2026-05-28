from unittest.mock import MagicMock, patch

from app.utils.queries_split.staff import StaffQueries


def _unknown_linia_error():
    return Exception("1054 (42S22): Unknown column 'linia' in 'where clause'")


def test_get_obsada_zmiany_with_section_falls_back_without_linia_column():
    cursor = MagicMock()
    cursor.execute.side_effect = [_unknown_linia_error(), None]
    cursor.fetchall.return_value = [(1, 'Jan Kowalski')]

    result = StaffQueries.get_obsada_zmiany('2026-05-28', sekcja='Zasyp', linia='PSD', cursor=cursor)

    assert result == [(1, 'Jan Kowalski')]
    assert cursor.execute.call_count == 2
    assert 'o.linia = %s' in cursor.execute.call_args_list[0].args[0]
    assert 'o.linia = %s' not in cursor.execute.call_args_list[1].args[0]


def test_get_obsada_zmiany_without_section_falls_back_without_linia_column():
    cursor = MagicMock()
    cursor.execute.side_effect = [_unknown_linia_error(), None]
    cursor.fetchall.return_value = [(7,)]

    result = StaffQueries.get_obsada_zmiany('2026-05-28', sekcja=None, linia='AGRO', cursor=cursor)

    assert result == [(7,)]
    assert cursor.execute.call_count == 2
    assert 'AND linia = %s' in cursor.execute.call_args_list[0].args[0]
    assert 'AND linia = %s' not in cursor.execute.call_args_list[1].args[0]


def test_get_obsada_for_date_falls_back_without_linia_column():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.execute.side_effect = [_unknown_linia_error(), None]
    cursor.fetchall.return_value = [('Zasyp', 1, 'Jan Kowalski')]

    with patch('app.utils.queries_split.staff.get_db_connection', return_value=conn):
        result = StaffQueries.get_obsada_for_date('2026-05-28', linia='PSD')

    assert result == {'Zasyp': [(1, 'Jan Kowalski')]}
    assert cursor.execute.call_count == 2
    assert 'oz.linia = %s' in cursor.execute.call_args_list[0].args[0]
    assert 'oz.linia = %s' not in cursor.execute.call_args_list[1].args[0]
    conn.close.assert_called_once()


def test_get_unassigned_pracownicy_falls_back_without_linia_column():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    cursor.execute.side_effect = [_unknown_linia_error(), None]
    cursor.fetchall.return_value = [(2, 'Anna Nowak')]

    with patch('app.utils.queries_split.staff.get_db_connection', return_value=conn):
        result = StaffQueries.get_unassigned_pracownicy('2026-05-28', linia='AGRO')

    assert result == [(2, 'Anna Nowak')]
    assert cursor.execute.call_count == 2
    assert 'AND linia=%s' in cursor.execute.call_args_list[0].args[0]
    assert 'AND linia=%s' not in cursor.execute.call_args_list[1].args[0]
    conn.close.assert_called_once()