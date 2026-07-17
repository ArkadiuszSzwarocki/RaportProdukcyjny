from unittest.mock import MagicMock, patch


def _prepare_session(client):
    with client.session_transaction() as sess:
        sess['zalogowany'] = True
        sess['login'] = 'operator.test'
        sess['rola'] = 'pracownik'
        sess['pracownik_id'] = 77
        sess['selected_hall_view'] = 'AGRO'


@patch('app.blueprints.routes_planning_creation.audit_log')
@patch('app.blueprints.routes_planning_creation.get_plan_notification_context', return_value={})
@patch('app.blueprints.routes_planning_creation.refresh_bufor_queue')
@patch('app.blueprints.routes_planning_creation.notify_laboratory_about_zasyp')
@patch('app.blueprints.routes_planning_creation.get_table_name')
@patch('app.blueprints.routes_planning_creation.get_db_connection')
def test_agro_manual_zasyp_syncs_missing_kontrolne_sessions(
    mock_get_conn,
    mock_get_table_name,
    mock_notify_lab,
    mock_refresh_bufor,
    mock_plan_ctx,
    mock_audit,
    client,
):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn
    mock_get_table_name.side_effect = lambda base, linia=None: {
        'plan_produkcji': 'plan_produkcji_agro',
        'szarze': 'szarze_agro',
        'dosypki': 'dosypki_agro',
    }.get(base, base)

    executed = []

    def execute(sql, params=None):
        executed.append((str(sql), params))

    def fetchone():
        sql = executed[-1][0] if executed else ''
        if 'SELECT MAX(nr_szarzy)' in sql:
            return (1,)
        if 'COUNT(DISTINCT szarza_nr) FROM zasyp_etapy' in sql:
            return (1,)
        if "SELECT id, tonaz, zasyp_id" in sql and "sekcja='Workowanie'" in sql:
            return (500, 1000, 123)
        if "SELECT id, tonaz FROM" in sql and "zasyp_id=%s AND sekcja='Workowanie'" in sql:
            return (500, 1000)
        return None

    mock_cursor.execute.side_effect = execute
    mock_cursor.fetchone.side_effect = fetchone

    _prepare_session(client)

    response = client.post(
        '/api/dodaj_plan',
        data={
            'data_planu': '2026-05-12',
            'produkt': 'AGRO TEST',
            'tonaz': '1200',
            'sekcja': 'Zasyp',
            'typ_produkcji': 'agro',
            'linia': 'AGRO',
            'plan_id': '123',
            'nr_szarzy': '2',
            'ui_trigger': 'test',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert any('INSERT INTO zasyp_etapy' in sql for sql, _ in executed)
    assert any('INSERT INTO szarze_agro' in sql for sql, _ in executed)

    sync_calls = [
        (sql, params)
        for sql, params in executed
        if 'INSERT INTO zasyp_etapy' in sql
    ]
    assert sync_calls, 'Expected synchronization INSERT into zasyp_etapy'
    _, sync_params = sync_calls[0]
    assert sync_params[0] == 'AGRO'
    assert sync_params[1] == 123
    assert sync_params[3] == 2
    assert sync_params[4] == 0


@patch('app.blueprints.routes_planning_creation.get_table_name')
@patch('app.blueprints.routes_planning_creation.get_db_connection')
def test_agro_manual_zasyp_still_rejects_out_of_order_number(mock_get_conn, mock_get_table_name, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn
    mock_get_table_name.side_effect = lambda base, linia=None: {
        'plan_produkcji': 'plan_produkcji_agro',
        'szarze': 'szarze_agro',
        'dosypki': 'dosypki_agro',
    }.get(base, base)

    executed = []

    def execute(sql, params=None):
        executed.append((str(sql), params))

    def fetchone():
        sql = executed[-1][0] if executed else ''
        if 'SELECT MAX(nr_szarzy)' in sql:
            return (5,)
        return None

    mock_cursor.execute.side_effect = execute
    mock_cursor.fetchone.side_effect = fetchone

    _prepare_session(client)

    response = client.post(
        '/api/dodaj_plan',
        data={
            'data_planu': '2026-05-12',
            'produkt': 'AGRO TEST',
            'tonaz': '1000',
            'sekcja': 'Zasyp',
            'typ_produkcji': 'agro',
            'linia': 'AGRO',
            'plan_id': '123',
            'nr_szarzy': '7',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert not any('INSERT INTO zasyp_etapy' in sql for sql, _ in executed)
    assert not any('INSERT INTO szarze_agro' in sql for sql, _ in executed)

    with client.session_transaction() as sess:
        flashes = sess.get('_flashes', [])
    assert any(cat == 'modal_error' and 'naruszenie kolejności' in msg for cat, msg in flashes)


@patch('app.blueprints.routes_planning_creation.get_table_name')
@patch('app.blueprints.routes_planning_creation.get_db_connection')
def test_agro_manual_zasyp_is_blocked_when_auto_mode_enabled(mock_get_conn, mock_get_table_name, client):
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_conn.return_value = mock_conn
    mock_get_table_name.side_effect = lambda base, linia=None: {
        'plan_produkcji': 'plan_produkcji_agro',
        'szarze': 'szarze_agro',
        'dosypki': 'dosypki_agro',
    }.get(base, base)

    executed = []

    def execute(sql, params=None):
        executed.append((str(sql), params))

    def fetchone():
        sql = executed[-1][0] if executed else ''
        if 'SELECT MAX(nr_szarzy)' in sql:
            return (1,)
        return None

    mock_cursor.execute.side_effect = execute
    mock_cursor.fetchone.side_effect = fetchone

    _prepare_session(client)

    response = client.post(
        '/api/dodaj_plan',
        data={
            'data_planu': '2026-05-12',
            'produkt': 'AGRO TEST',
            'tonaz': '1000',
            'sekcja': 'Zasyp',
            'typ_produkcji': 'agro',
            'linia': 'AGRO',
            'plan_id': '123',
            'nr_szarzy': '2',
            'auto_szarza_mode': 'auto',
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert not any('INSERT INTO zasyp_etapy' in sql for sql, _ in executed)
    assert not any('INSERT INTO szarze_agro' in sql for sql, _ in executed)

    with client.session_transaction() as sess:
        flashes = sess.get('_flashes', [])
    assert any(cat == 'modal_error' and 'AUTO SZARŻA' in msg for cat, msg in flashes)
