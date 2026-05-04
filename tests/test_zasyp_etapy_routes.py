import pytest
from datetime import date
from unittest.mock import MagicMock, patch


@pytest.mark.usefixtures("app")
class TestZasypEtapStartRoute:
    @patch('app.blueprints.routes_production.generate_tts_async')
    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.set_wielkosc_szarzy')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_start_etap_invokes_service(self, mock_get_conn, mock_get_table_name, mock_start_etap, mock_set_szarza, mock_audit_log, mock_generate_tts, client, app):
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
                szarza_nr=None,
            )
            # Route may open additional internal DB connections (np. powiadomienia/TTS),
            # więc asercja potwierdza domknięcie bez zakładania pojedynczego wywołania.
            assert mock_conn.close.called
            mock_audit_log.assert_called_once_with('START etapu Zasyp', 'plan_id=123, etap=1, linia=PSD, produkt=Produkt testowy')


@pytest.mark.usefixtures("app")
class TestZasypEtapStopRoute:
    @patch('app.blueprints.routes_production.generate_tts_async')
    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.ZasypEtapyService.stop_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_stop_etap_starts_next_stage(self, mock_get_conn, mock_get_table_name, mock_stop_etap, mock_start_etap, mock_audit_log, mock_generate_tts, client, app):
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
            mock_stop_etap.assert_called_once_with(plan_id=123, linia='PSD', etap=1, user_login='test.user', szarza_nr=None)
            mock_start_etap.assert_called_once_with(
                plan_id=123,
                linia='PSD',
                data_planu=date(2026, 4, 22),
                etap=2,
                user_login='test.user',
                szarza_nr=None,
            )
            # Route może uruchamiać dodatkowe ścieżki z własnymi połączeniami DB.
            assert mock_conn.close.called
            mock_audit_log.assert_any_call('STOP etapu Zasyp', 'plan_id=123, etap=1, linia=PSD, produkt=Produkt testowy')
            mock_audit_log.assert_any_call('START etapu Zasyp', 'plan_id=123, etap=2, linia=PSD, produkt=Produkt testowy')

    @patch('app.blueprints.routes_production.generate_tts_async')
    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.ZasypEtapyService.stop_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_stop_last_etap_does_not_start_next(self, mock_get_conn, mock_get_table_name, mock_stop_etap, mock_start_etap, mock_audit_log, mock_generate_tts, client, app):
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
            mock_stop_etap.assert_called_once_with(plan_id=123, linia='PSD', etap=6, user_login='test.user', szarza_nr=None)
            mock_start_etap.assert_not_called()
            mock_audit_log.assert_called_once_with('STOP etapu Zasyp', 'plan_id=123, etap=6, linia=PSD, produkt=Produkt testowy')

    @patch('app.blueprints.routes_production.generate_tts_async')
    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.ZasypEtapyService.stop_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_agro_stop_etap_2_does_not_auto_start_next(self, mock_get_conn, mock_get_table_name, mock_stop_etap, mock_start_etap, mock_audit_log, mock_generate_tts, client, app):
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
            mock_stop_etap.assert_called_once_with(plan_id=123, linia='AGRO', etap=2, user_login='test.user', szarza_nr=None)
            mock_start_etap.assert_not_called()
            mock_audit_log.assert_any_call('STOP etapu Zasyp', 'plan_id=123, etap=2, linia=AGRO, produkt=Produkt testowy')

    @patch('app.blueprints.routes_production.generate_tts_async')
    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.kolejny_pomiar')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.ZasypEtapyService.stop_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_agro_stop_etap_3_starts_etap_4(self, mock_get_conn, mock_get_table_name, mock_stop_etap, mock_start_etap, mock_kolejny_pomiar, mock_audit_log, mock_generate_tts, client, app):
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ('Zasyp', 'w toku', date(2026, 4, 22), 'Produkt testowy')
            mock_get_conn.return_value = mock_conn
            mock_get_table_name.return_value = 'plan_produkcji_agro'
            mock_stop_etap.return_value = (True, 'Stop etapu 4 zapisany')
            mock_start_etap.return_value = (True, 'Start etapu 5 zapisany')
            mock_kolejny_pomiar.return_value = (True, 'Przełączono pomiar na szarżę #2')

            with client.session_transaction() as sess:
                sess['zalogowany'] = True
                sess['login'] = 'test.user'
                sess['rola'] = 'pracownik'
                sess['selected_hall_view'] = 'AGRO'

            response = client.post(
                '/zasyp_etap_stop',
                data={'plan_id': '123', 'etap': '4', 'linia': 'AGRO', 'sekcja': 'Zasyp', 'next_action': 'oprozniamy'},
                follow_redirects=False,
            )

            assert response.status_code == 302
            mock_stop_etap.assert_called_once_with(plan_id=123, linia='AGRO', etap=4, user_login='test.user', szarza_nr=None)
            mock_start_etap.assert_called_once_with(
                plan_id=123,
                linia='AGRO',
                data_planu=date(2026, 4, 22),
                etap=5,
                user_login='test.user',
                szarza_nr=None,
            )
            mock_audit_log.assert_any_call('STOP etapu Zasyp', 'plan_id=123, etap=4, linia=AGRO, produkt=Produkt testowy')
            mock_audit_log.assert_any_call('START etapu Zasyp', 'plan_id=123, etap=5, linia=AGRO, produkt=Produkt testowy')

    @patch('app.blueprints.routes_production.generate_tts_async')
    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.kolejny_pomiar')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.ZasypEtapyService.stop_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_agro_stop_oprozniania_allows_new_point_choice(self, mock_get_conn, mock_get_table_name, mock_stop_etap, mock_start_etap, mock_kolejny_pomiar, mock_audit_log, mock_generate_tts, client, app):
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_cursor.fetchone.return_value = ('Zasyp', 'w toku', date(2026, 4, 22), 'Produkt testowy')
            mock_get_conn.return_value = mock_conn
            mock_get_table_name.return_value = 'plan_produkcji_agro'
            mock_stop_etap.return_value = (True, 'Stop etapu 5 zapisany')
            mock_kolejny_pomiar.return_value = (True, 'Przełączono pomiar na szarżę #2')

            with client.session_transaction() as sess:
                sess['zalogowany'] = True
                sess['login'] = 'test.user'
                sess['rola'] = 'pracownik'
                sess['selected_hall_view'] = 'AGRO'

            response = client.post(
                '/zasyp_etap_stop',
                data={'plan_id': '123', 'etap': '5', 'linia': 'AGRO', 'sekcja': 'Zasyp', 'next_action': 'new_point'},
                follow_redirects=False,
            )

            assert response.status_code == 302
            mock_stop_etap.assert_called_once_with(plan_id=123, linia='AGRO', etap=5, user_login='test.user', szarza_nr=None)
            mock_start_etap.assert_not_called()
            mock_kolejny_pomiar.assert_called_once_with(123, 'AGRO', 'test.user')
            mock_audit_log.assert_called_once_with('STOP etapu Zasyp', 'plan_id=123, etap=5, linia=AGRO, produkt=Produkt testowy')


@pytest.mark.usefixtures("app")
class TestZasypEtapySummaryRoute:
    @patch('app.blueprints.routes_production.ZasypEtapyService.get_zlecenia_summary')
    @patch('app.blueprints.routes_production.ZasypEtapyService.get_summary')
    def test_laborant_can_open_zasyp_time_report(self, mock_get_summary, mock_get_zlecenia_summary, client):
        mock_get_summary.return_value = []
        mock_get_zlecenia_summary.return_value = []

        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['login'] = 'lab.user'
            sess['rola'] = 'laborant'
            sess['selected_hall_view'] = 'AGRO'

        response = client.get('/zasyp_etapy_podsumowanie?linia=AGRO', follow_redirects=False)

        assert response.status_code == 200
        assert 'Podsumowanie etapów Zasyp'.encode('utf-8') in response.data
        mock_get_summary.assert_called_once()
        mock_get_zlecenia_summary.assert_called_once()


@pytest.mark.usefixtures("app")
class TestZasypLaboratoryNotifications:
    @patch('app.blueprints.routes_production.add_mieszanie_event')
    @patch('app.blueprints.routes_production.generate_tts_async')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_notify_laboratory_emits_event_for_agro_dosypka_stage(
        self,
        mock_get_conn,
        mock_get_table_name,
        mock_generate_tts,
        mock_add_mieszanie_event,
        app,
    ):
        from app.blueprints import routes_production

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (7,)
        mock_get_conn.return_value = mock_conn
        mock_get_table_name.return_value = 'szarze_agro'

        with app.app_context():
            routes_production._notify_laboratory_stage_start('AGRO', 123, 31, 'Mleko BIALE', szarza_nr=4)

        assert mock_generate_tts.called
        mock_add_mieszanie_event.assert_called_once()
        called_args = mock_add_mieszanie_event.call_args[0]
        assert called_args[0] == 'AGRO'
        assert called_args[1] == 123
        assert called_args[2] == 31
        assert called_args[4] == 4

    def test_build_mieszanie_tts_text_for_dosypka_stage(self):
        from app.services.zasyp_mieszanie_notification_service import build_mieszanie_tts_text

        text = build_mieszanie_tts_text('Mleko BIALE', 1, 31)
        assert 'rozpoczął dosypkę do mieszania' in text.lower()
        assert 'mleko białe' in text.lower()


@pytest.mark.usefixtures("app")
class TestAutoSzarzaGuards:
    @patch('app.blueprints.routes_production._notify_laboratory_stage_start')
    @patch('app.blueprints.routes_production._insert_szarza_compatible')
    @patch('app.blueprints.routes_production.generate_tts_async')
    @patch('app.blueprints.routes_production.audit_log')
    @patch('app.blueprints.routes_production.ZasypEtapyService.set_wielkosc_szarzy')
    @patch('app.blueprints.routes_production.ZasypEtapyService.start_etap')
    @patch('app.blueprints.routes_production.get_table_name')
    @patch('app.blueprints.routes_production.get_db_connection')
    def test_start_etap_auto_does_not_add_duplicate_existing_szarza(
        self,
        mock_get_conn,
        mock_get_table_name,
        mock_start_etap,
        mock_set_szarza,
        mock_audit_log,
        mock_generate_tts,
        mock_insert_szarza,
        mock_notify,
        client,
        app,
    ):
        with app.app_context():
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            # 1) plan check in route, 2) existing szarza check in auto block
            mock_cursor.fetchone.side_effect = [
                ('Zasyp', 'w toku', date(2026, 4, 22), 'Produkt testowy', 'agro'),
                (999,),
            ]
            mock_get_conn.return_value = mock_conn
            mock_get_table_name.side_effect = lambda base, linia=None: {
                'plan_produkcji': 'plan_produkcji_agro',
                'szarze': 'szarze_agro',
                'dosypki': 'dosypki_agro',
            }.get(base, base)
            mock_start_etap.return_value = (True, 'Start etapu 1 zapisany')
            mock_set_szarza.return_value = (True, 'Zapisano wielkość szarży')

            with client.session_transaction() as sess:
                sess['zalogowany'] = True
                sess['login'] = 'test.user'
                sess['rola'] = 'pracownik'
                sess['selected_hall_view'] = 'AGRO'
                sess['pracownik_id'] = 55

            response = client.post(
                '/zasyp_etap_start',
                data={
                    'plan_id': '123',
                    'etap': '1',
                    'linia': 'AGRO',
                    'sekcja': 'Zasyp',
                    'data_planu': '2026-04-22',
                    'wielkosc_szarzy_kg': '1500',
                    'szarza_nr': '2',
                    'auto_szarza_mode': 'auto',
                },
                follow_redirects=False,
            )

            assert response.status_code == 302
            mock_insert_szarza.assert_not_called()
            # ensure duplicate check targeted the same current szarza (2), not MAX+1
            assert any(
                'FROM szarze_agro WHERE plan_id=%s AND nr_szarzy=%s LIMIT 1' in str(call.args[0]) and call.args[1] == (123, 2)
                for call in mock_cursor.execute.call_args_list
            )

    @patch('app.blueprints.routes_production.ZasypEtapyService.kolejny_pomiar')
    @patch('app.blueprints.routes_production._insert_szarza_compatible')
    def test_kolejny_pomiar_does_not_create_batch_even_in_auto_mode(
        self,
        mock_insert_szarza,
        mock_kolejny_pomiar,
        client,
    ):
        mock_kolejny_pomiar.return_value = (True, 'Przełączono pomiar na szarżę #2')

        with client.session_transaction() as sess:
            sess['zalogowany'] = True
            sess['login'] = 'test.user'
            sess['rola'] = 'pracownik'
            sess['selected_hall_view'] = 'AGRO'
            sess['pracownik_id'] = 77

        response = client.post(
            '/zasyp_kolejny_pomiar/123',
            data={'linia': 'AGRO', 'auto_szarza_mode': 'auto'},
            follow_redirects=False,
        )

        assert response.status_code == 302
        mock_insert_szarza.assert_not_called()
