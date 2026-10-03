# cspell:words nawazanie nawazania
"""Only assigned materials may become bucket ingredients or touch buttons."""
from unittest.mock import MagicMock, patch
import pytest
from app.services.bucket_maluch_service import BucketMaluchService


@pytest.mark.parametrize('submitted_name', [None, 'Invented material'])
def test_unassigned_station_cannot_add_even_with_submitted_material(submitted_name):
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_id', return_value={'id': 1, 'status': 'w_trakcie_nawazania', 'linia': 'AGRO'}), patch.object(
            BucketMaluchService, 'get_station_material', return_value=''), patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.add_item') as add:
        success, message, _ = BucketMaluchService.add_item_to_bucket(1, 'KO30', submitted_name)
    assert success is False
    assert 'nie ma przypisanego surowca' in message
    add.assert_not_called()


def test_material_is_resolved_from_actual_bucket_hall():
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_id', return_value={'id': 1, 'status': 'w_trakcie_nawazania', 'linia': 'AGRO'}), patch.object(
            BucketMaluchService, 'get_station_material', return_value='Assigned') as resolve, patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.add_item') as add:
        assert BucketMaluchService.add_item_to_bucket(1, 'KO01', linia='PSD')[0] is True
    resolve.assert_called_once_with('KO01', 'AGRO')
    assert add.call_args.kwargs['surowiec_nazwa'] == 'Assigned'


def test_submitted_name_cannot_override_assignment():
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_id', return_value={'id': 1, 'status': 'w_trakcie_nawazania', 'linia': 'AGRO'}), patch.object(
            BucketMaluchService, 'get_station_material', return_value='Assigned'), patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.add_item') as add:
        assert not BucketMaluchService.add_item_to_bucket(1, 'KO01', 'Other')[0]
    add.assert_not_called()


def test_assignment_sources_exclude_history_empty_stock_and_placeholders():
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.side_effect = [
        [{'kod_zbiornika': 'KO01', 'nazwa_surowca': 'Assigned'}, {'kod_zbiornika': 'KO30', 'nazwa_surowca': 'Surowiec ze stacji KO30'}],
        [{'lokalizacja': 'KO04', 'nazwa': 'Current'}]]
    with patch('app.services.bucket_maluch_service.get_db_connection', return_value=connection), patch(
            'app.services.agro.agro_tanks_service.AgroTanksService.get_production_inventory_snapshot', return_value=[
                {'zbiornik': 'KO05', 'surowiec_nazwa': 'Production', 'stan_systemowy': 1},
                {'zbiornik': 'KO06', 'surowiec_nazwa': 'Empty', 'stan_systemowy': 0}]):
        assert BucketMaluchService.get_assigned_station_materials('AGRO') == {'KO01': 'Assigned', 'KO04': 'Current', 'KO05': 'Production'}
    assert cursor.execute.call_count == 2
    assert cursor.execute.call_args.args[1] == ('AGRO',)
    assert 'stan_magazynowy>0' in cursor.execute.call_args.args[0]


def test_assignment_read_error_never_generates_a_material():
    connection = MagicMock()
    connection.cursor.return_value.execute.side_effect = RuntimeError('Test')
    with patch('app.services.bucket_maluch_service.get_db_connection', return_value=connection):
        assert BucketMaluchService.get_station_material('KO30', 'AGRO') == ''


def test_page_only_renders_assigned_station_buttons(client):
    with client.session_transaction() as session:
        session.update(zalogowany=True, rola='masteradmin', selected_hall_view='AGRO')
    connection = MagicMock()
    connection.cursor.return_value.fetchall.side_effect = [[], [], []]
    with patch('app.blueprints.maluchy.routes.get_db_connection', return_value=connection), patch.object(
            BucketMaluchService, 'get_assigned_station_materials', return_value={'KO01': 'Assigned', 'BB01': 'Other'}):
        response = client.get('/maluchy/nawazanie?linia=AGRO')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-stacja="KO01"' in html
    assert 'data-stacja="KO30"' not in html
    assert 'data-stacja="KO35"' not in html
    assert 'data-stacja="KO38"' not in html
