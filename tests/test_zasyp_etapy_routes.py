import pytest
from datetime import date
from unittest.mock import MagicMock, patch


@pytest.mark.usefixtures("app")
class TestZasypEtapStartRoute:
    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.set_wielkosc_szarzy')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_start_etap_invokes_service(self, mock_get_conn, mock_get_table_name, mock_start_etap, mock_set_szarza, mock_audit_log, client, app):
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ('Zasyp', 'w toku', date(2026, 4, 22), 'Produkt testowy')
            mock_get_conn.return_value = mock_conn
            mock_get_table_name.return_value = 'plan_produkcji_psd'
            mock_start_etap.return_value = (True, 'Start etapu 1 zapisany')
            mock_set_szarza.return_value = (True, 'Zapisano wielkość szarży')

            with client.session_transaction() as sess:
                sess['zalogowany'] = True
                sess['login'] = 'test.user'
                sess['rola'] = 'pracownik'
                sess['selected_hall_view'] = 'PSD'

            response = client.post(
                '/zasyp_etap_start',
                data={'plan_id': '123', 'etap': '1', 'linia': 'PSD', 'sekcja': 'Zasyp', 'data_planu': '2026-04-22', 'wielkosc_szarzy_kg': '1000'},
                follow_redirects=False,
            )

            assert response.status_code == 302
            mock_set_szarza.assert_called_once_with(
                plan_id=123,
                linia='PSD',
                data_planu=date(2026, 4, 22),
                kg=1000.0,
                user_login='test.user',
            )
            mock_start_etap.assert_called_once_with(
                plan_id=123,
                linia='PSD',
                data_planu=date(2026, 4, 22),
                etap=1,
                user_login='test.user',
            )
            mock_conn.close.assert_called_once()
            mock_audit_log.assert_called_once_with('START etapu Zasyp', 'plan_id=123, etap=1, linia=PSD, produkt=Produkt testowy')


@pytest.mark.usefixtures("app")
class TestZasypEtapStopRoute:
    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.ZasypEtapyService.stop_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_stop_etap_starts_next_stage(self, mock_get_conn, mock_get_table_name, mock_stop_etap, mock_start_etap, mock_audit_log, client, app):
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ('Zasyp', 'w toku', date(2026, 4, 22), 'Produkt testowy')
            mock_get_conn.return_value = mock_conn
            mock_get_table_name.return_value = 'plan_produkcji_psd'
            mock_stop_etap.return_value = (True, 'Stop etapu 1 zapisany')
            mock_start_etap.return_value = (True, 'Start etapu 2 zapisany')

            with client.session_transaction() as sess:
                sess['zalogowany'] = True
                sess['login'] = 'test.user'
                sess['rola'] = 'pracownik'
                sess['selected_hall_view'] = 'PSD'

            response = client.post(
                '/zasyp_etap_stop',
                data={'plan_id': '123', 'etap': '1', 'linia': 'PSD', 'sekcja': 'Zasyp'},
                follow_redirects=False,
            )

            assert response.status_code == 302
            mock_stop_etap.assert_called_once_with(plan_id=123, linia='PSD', etap=1, user_login='test.user')
            mock_start_etap.assert_called_once_with(
                plan_id=123,
                linia='PSD',
                data_planu=date(2026, 4, 22),
                etap=2,
                user_login='test.user',
            )
            mock_conn.close.assert_called_once()
            mock_audit_log.assert_any_call('STOP etapu Zasyp', 'plan_id=123, etap=1, linia=PSD, produkt=Produkt testowy')
            mock_audit_log.assert_any_call('START etapu Zasyp', 'plan_id=123, etap=2, linia=PSD, produkt=Produkt testowy')

    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.ZasypEtapyService.stop_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_stop_last_etap_does_not_start_next(self, mock_get_conn, mock_get_table_name, mock_stop_etap, mock_start_etap, mock_audit_log, client, app):
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ('Zasyp', 'w toku', date(2026, 4, 22), 'Produkt testowy')
            mock_get_conn.return_value = mock_conn
            mock_get_table_name.return_value = 'plan_produkcji_psd'
            mock_stop_etap.return_value = (True, 'Stop etapu 6 zapisany')

            with client.session_transaction() as sess:
                sess['zalogowany'] = True
                sess['login'] = 'test.user'
                sess['rola'] = 'pracownik'
                sess['selected_hall_view'] = 'PSD'

            response = client.post(
                '/zasyp_etap_stop',
                data={'plan_id': '123', 'etap': '6', 'linia': 'PSD', 'sekcja': 'Zasyp'},
                follow_redirects=False,
            )

            assert response.status_code == 302
            mock_stop_etap.assert_called_once_with(plan_id=123, linia='PSD', etap=6, user_login='test.user')
            mock_start_etap.assert_not_called()
            mock_audit_log.assert_called_once_with('STOP etapu Zasyp', 'plan_id=123, etap=6, linia=PSD, produkt=Produkt testowy')

    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.ZasypEtapyService.stop_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_agro_stop_etap_2_does_not_auto_start_next(self, mock_get_conn, mock_get_table_name, mock_stop_etap, mock_start_etap, mock_audit_log, client, app):
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ('Zasyp', 'w toku', date(2026, 4, 22), 'Produkt testowy')
            mock_get_conn.return_value = mock_conn
            mock_get_table_name.return_value = 'plan_produkcji_agro'
            mock_stop_etap.return_value = (True, 'Stop etapu 2 zapisany')

            with client.session_transaction() as sess:
                sess['zalogowany'] = True
                sess['login'] = 'test.user'
                sess['rola'] = 'pracownik'
                sess['selected_hall_view'] = 'AGRO'

            response = client.post(
                '/zasyp_etap_stop',
                data={'plan_id': '123', 'etap': '2', 'linia': 'AGRO', 'sekcja': 'Zasyp'},
                follow_redirects=False,
            )

            assert response.status_code == 302
            mock_stop_etap.assert_called_once_with(plan_id=123, linia='AGRO', etap=2, user_login='test.user')
            mock_start_etap.assert_not_called()
            mock_audit_log.assert_any_call('STOP etapu Zasyp', 'plan_id=123, etap=2, linia=AGRO, produkt=Produkt testowy')

    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.ZasypEtapyService.stop_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_agro_stop_etap_3_starts_etap_4(self, mock_get_conn, mock_get_table_name, mock_stop_etap, mock_start_etap, mock_audit_log, client, app):
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ('Zasyp', 'w toku', date(2026, 4, 22), 'Produkt testowy')
            mock_get_conn.return_value = mock_conn
            mock_get_table_name.return_value = 'plan_produkcji_agro'
            mock_stop_etap.return_value = (True, 'Stop etapu 4 zapisany')
            mock_start_etap.return_value = (True, 'Start etapu 5 zapisany')

            with client.session_transaction() as sess:
                sess['zalogowany'] = True
                sess['login'] = 'test.user'
                sess['rola'] = 'pracownik'
                sess['selected_hall_view'] = 'AGRO'

            response = client.post(
                '/zasyp_etap_stop',
                data={'plan_id': '123', 'etap': '4', 'linia': 'AGRO', 'sekcja': 'Zasyp'},
                follow_redirects=False,
            )

            assert response.status_code == 302
            mock_stop_etap.assert_called_once_with(plan_id=123, linia='AGRO', etap=4, user_login='test.user')
            mock_start_etap.assert_called_once_with(
                plan_id=123,
                linia='AGRO',
                data_planu=date(2026, 4, 22),
                etap=5,
                user_login='test.user',
            )
            mock_audit_log.assert_any_call('STOP etapu Zasyp', 'plan_id=123, etap=4, linia=AGRO, produkt=Produkt testowy')
            mock_audit_log.assert_any_call('START etapu Zasyp', 'plan_id=123, etap=5, linia=AGRO, produkt=Produkt testowy')
