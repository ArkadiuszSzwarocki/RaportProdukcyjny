"""Security regression tests for session tracking."""

from unittest.mock import MagicMock, patch

from app.repositories.session_repository import (
    deactivate_all_user_sessions,
    is_session_active,
)


def _connection_with_row(row):
    cursor = MagicMock()
    cursor.fetchone.return_value = row

    connection = MagicMock()
    connection.cursor.return_value = cursor
    return connection, cursor


def test_is_session_active_returns_true_only_for_active_session_and_user():
    connection, cursor = _connection_with_row((1, 1))

    with patch(
        'app.repositories.session_repository.get_db_connection',
        return_value=connection,
    ):
        assert is_session_active('session-123') is True

    cursor.execute.assert_called_once()
    connection.close.assert_called_once()


def test_is_session_active_missing_db_record_fails_closed():
    connection, _ = _connection_with_row(None)

    with patch(
        'app.repositories.session_repository.get_db_connection',
        return_value=connection,
    ):
        assert is_session_active('missing-session') is False


def test_is_session_active_inactive_session_or_user_fails_closed():
    for row in ((0, 1), (1, 0), (0, 0)):
        connection, _ = _connection_with_row(row)
        with patch(
            'app.repositories.session_repository.get_db_connection',
            return_value=connection,
        ):
            assert is_session_active('inactive-session') is False


def test_is_session_active_database_error_fails_closed():
    with patch(
        'app.repositories.session_repository.get_db_connection',
        side_effect=RuntimeError('database unavailable'),
    ):
        assert is_session_active('session-123') is False


def test_deactivate_all_user_sessions_can_preserve_current_session():
    connection, cursor = _connection_with_row(None)

    with patch(
        'app.repositories.session_repository.get_db_connection',
        return_value=connection,
    ):
        result = deactivate_all_user_sessions(42, except_session_id='keep-me')

    assert result is True
    sql, params = cursor.execute.call_args.args
    assert 'session_id != %s' in sql
    assert params == (42, 'keep-me')
    connection.commit.assert_called_once()
    connection.close.assert_called_once()


def test_deactivate_all_user_sessions_without_exception_id_logs_out_every_session():
    connection, cursor = _connection_with_row(None)

    with patch(
        'app.repositories.session_repository.get_db_connection',
        return_value=connection,
    ):
        result = deactivate_all_user_sessions(42)

    assert result is True
    sql, params = cursor.execute.call_args.args
    assert 'session_id != %s' not in sql
    assert params == (42,)
    connection.commit.assert_called_once()


def test_deactivate_all_user_sessions_rolls_back_on_error():
    connection = MagicMock()
    cursor = MagicMock()
    cursor.execute.side_effect = RuntimeError('update failed')
    connection.cursor.return_value = cursor

    with patch(
        'app.repositories.session_repository.get_db_connection',
        return_value=connection,
    ):
        result = deactivate_all_user_sessions(42, except_session_id='keep-me')

    assert result is False
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
