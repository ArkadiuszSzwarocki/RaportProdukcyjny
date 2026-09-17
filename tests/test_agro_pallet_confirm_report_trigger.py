import pytest
from unittest.mock import MagicMock, patch
from flask import Flask, session
from app.services.magazyn_dostawy.acceptance_service import AcceptanceService
from app.services.warehouse_pallet_service import WarehousePalletService

def test_acceptance_service_triggers_report_on_last_pallet_closed_agro():
    """Weryfikuje, że AcceptanceService zwraca open_report_url gdy magazynier przyjmie ostatnią paletę z zamkniętego zlecenia AGRO."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    fake_agro_pallet = {
        'id': 700,
        'plan_id': 350,
        'nr_palety': 'AGR000001787139218902',
        'waga': 1000.0,
        'waga_brutto': 1025.0,
        'tara': 25.0,
        'status': 'do_przyjecia',
        'produkt_nazwa': 'AGRO PASZA MAX',
        'produkt': 'AGRO PASZA MAX',
        'data_planu': '2026-09-14'
    }

    def fake_fetchone():
        if mock_cursor.execute.call_args:
            sql = str(mock_cursor.execute.call_args[0][0])
            if 'palety_agro' in sql and 'WHERE' in sql and ('p.nr_palety' in sql or 'p.id' in sql):
                return fake_agro_pallet
            if 'SELECT id FROM magazyn_palety_agro' in sql:
                return None
            if 'SELECT status, sekcja FROM plan_produkcji_agro' in sql:
                return {'status': 'zakończone', 'sekcja': 'Workowanie'}
            if 'SELECT COUNT(*) as total FROM palety_agro' in sql:
                return {'total': 5}
            if 'SELECT COUNT(*) as received FROM palety_agro' in sql:
                return {'received': 5}
        return None

    mock_cursor.fetchone.side_effect = fake_fetchone

    with patch('app.services.magazyn_dostawy.acceptance_service.get_db_connection', return_value=mock_conn):
        with patch('app.services.office_print_service.trigger_office_print') as mock_office_print:
            res = AcceptanceService.accept_production_pallet(
                pallet_id=700,
                lokalizacja='MGW01',
                linia='AGRO',
                login='magazynier_test',
                confirmed_weight=1000.0
            )

            # Test kompatybilności rozpakowania krotki (ok, msg)
            ok, msg = res[0], res[1]
            assert ok is True
            assert getattr(res, 'is_last_pallet', False) is True
            assert getattr(res, 'open_report_url', None) == "/agro/raport_palet?plan_id=350&autoprint=1"
            mock_office_print.assert_called_once_with(350, typ_raportu='raport_palet_agro')

def test_acceptance_service_does_not_trigger_report_if_not_last_pallet():
    """Weryfikuje, że jeśli to nie jest ostatnia paleta, open_report_url nie jest ustawiony."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    fake_agro_pallet = {
        'id': 701,
        'plan_id': 350,
        'nr_palety': 'AGR000001787139218903',
        'waga': 1000.0,
        'waga_brutto': 1025.0,
        'tara': 25.0,
        'status': 'do_przyjecia',
        'produkt_nazwa': 'AGRO PASZA MAX',
        'produkt': 'AGRO PASZA MAX',
        'data_planu': '2026-09-14'
    }

    def fake_fetchone():
        if mock_cursor.execute.call_args:
            sql = str(mock_cursor.execute.call_args[0][0])
            if 'palety_agro' in sql and 'WHERE' in sql and ('p.nr_palety' in sql or 'p.id' in sql):
                return fake_agro_pallet
            if 'SELECT id FROM magazyn_palety_agro' in sql:
                return None
            if 'SELECT status, sekcja FROM plan_produkcji_agro' in sql:
                return {'status': 'zakończone', 'sekcja': 'Workowanie'}
            if 'SELECT COUNT(*) as total FROM palety_agro' in sql:
                return {'total': 5}
            if 'SELECT COUNT(*) as received FROM palety_agro' in sql:
                return {'received': 4}  # Jeszcze 1 paleta została
        return None

    mock_cursor.fetchone.side_effect = fake_fetchone

    with patch('app.services.magazyn_dostawy.acceptance_service.get_db_connection', return_value=mock_conn):
        res = AcceptanceService.accept_production_pallet(
            pallet_id=701,
            lokalizacja='MGW01',
            linia='AGRO',
            login='magazynier_test',
            confirmed_weight=1000.0
        )

        assert res[0] is True
        assert getattr(res, 'is_last_pallet', False) is False
        assert getattr(res, 'open_report_url', None) is None

def test_warehouse_pallet_service_potwierdz_palete_last_pallet_agro_ajax():
    """Weryfikuje, że WarehousePalletService.potwierdz_palete zwraca open_report_url w odpowiedzi AJAX."""
    app = Flask(__name__)
    app.secret_key = 'test-secret'

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    def fake_fetchone():
        if mock_cur.execute.call_args:
            sql = str(mock_cur.execute.call_args[0][0])
            if 'COALESCE(tara' in sql:
                return (25,)
            if 'SELECT waga FROM' in sql:
                return (1000,)
            if 'nr_plomby FROM' in sql:
                return (350, 'do_przyjecia', 1000, 'AGR-PAL-1', None)
            if 'data_planu, produkt, data_produkcji' in sql:
                return ('2026-09-14', 'AGRO PASZA MAX', '2026-09-14')
            if 'LIKE \'nr_palety_lp\'' in sql:
                return None
            if 'status, sekcja FROM' in sql:
                return ('zakończone', 'Workowanie')
            if 'COUNT(id) FROM' in sql and 'status IN' in sql:
                return (5,)
            if 'COUNT(id) FROM' in sql:
                return (5,)
        return None

    mock_cur.fetchone.side_effect = fake_fetchone
    mock_cur.rowcount = 1

    with app.test_request_context(method='POST', data={'waga_palety': '1000'}):
        session['rola'] = 'magazynier'
        session['login'] = 'magazynier_test'

        with patch('app.services.warehouse_pallet_service.get_db_connection', return_value=mock_conn):
            with patch('app.services.office_print_service.trigger_office_print') as mock_office_print:
                result, status_code, redirect_url = WarehousePalletService.potwierdz_palete(
                    paleta_id=50,
                    linia='AGRO',
                    user_login='magazynier_test',
                    app_obj=app,
                    update_paleta_workowanie=None,
                    update_paleta_magazyn=None,
                    is_ajax=True,
                    safe_return_url='/magazyn'
                )

                assert status_code == 200
                assert isinstance(result, dict)
                assert result.get('success') is True
                assert result.get('is_last_pallet') is True
                assert result.get('plan_id') == 350
                assert '/agro/raport_palet' in result.get('open_report_url', '')
                assert 'autoprint=1' in result.get('open_report_url', '')
                mock_office_print.assert_called_once_with(350, typ_raportu='raport_palet_agro')

def test_warehouse_pallet_service_potwierdz_palete_last_pallet_agro_non_ajax():
    """Weryfikuje, że dla żądania non-AJAX funkcja przekierowuje (302) bezpośrednio do open_report_url."""
    app = Flask(__name__)
    app.secret_key = 'test-secret'

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.cursor.return_value = mock_cur

    def fake_fetchone():
        if mock_cur.execute.call_args:
            sql = str(mock_cur.execute.call_args[0][0])
            if 'COALESCE(tara' in sql:
                return (25,)
            if 'SELECT waga FROM' in sql:
                return (1000,)
            if 'nr_plomby FROM' in sql:
                return (350, 'do_przyjecia', 1000, 'AGR-PAL-1', None)
            if 'data_planu, produkt, data_produkcji' in sql:
                return ('2026-09-14', 'AGRO PASZA MAX', '2026-09-14')
            if 'LIKE \'nr_palety_lp\'' in sql:
                return None
            if 'status, sekcja FROM' in sql:
                return ('zakończone', 'Workowanie')
            if 'COUNT(id) FROM' in sql and 'status IN' in sql:
                return (5,)
            if 'COUNT(id) FROM' in sql:
                return (5,)
        return None

    mock_cur.fetchone.side_effect = fake_fetchone
    mock_cur.rowcount = 1

    with app.test_request_context(method='POST', data={'waga_palety': '1000'}):
        session['rola'] = 'magazynier'
        session['login'] = 'magazynier_test'

        with patch('app.services.warehouse_pallet_service.get_db_connection', return_value=mock_conn):
            with patch('app.services.office_print_service.trigger_office_print'):
                result, status_code, redirect_url = WarehousePalletService.potwierdz_palete(
                    paleta_id=50,
                    linia='AGRO',
                    user_login='magazynier_test',
                    app_obj=app,
                    update_paleta_workowanie=None,
                    update_paleta_magazyn=None,
                    is_ajax=False,
                    safe_return_url='/magazyn'
                )

                assert status_code == 302
                assert '/agro/raport_palet' in redirect_url
                assert 'autoprint=1' in redirect_url
