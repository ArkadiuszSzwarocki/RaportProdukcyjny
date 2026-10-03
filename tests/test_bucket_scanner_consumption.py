# cspell:words sscc
# cspell:ignore MAL04OLD MAL04UNKNOWN
"""Consumed labels must never resolve or consume a fresh filling of the same bucket."""
from unittest.mock import MagicMock, patch
import pytest
from app.services.scanner.scanner_resolution_service import ScannerResolutionService
from app.services.bucket_maluch_service import BucketMaluchService


def bucket(status='wrzucone_do_mieszalnika'):
    return {'id': 1, 'kod_wiadra': '04', 'nr_sscc': 'MAL04OLD', 'plan_id': 123,
            'linia': 'AGRO', 'status': status, 'mieszalnik_kod': 'MI01',
            'pozycje': [{'stacja_kod': 'KO01', 'surowiec_nazwa': 'TEST'}]}


@pytest.mark.parametrize('status,used,quantity', [
    ('wrzucone_do_mieszalnika', True, 0), ('skompletowane', False, 1)])
def test_label_status_controls_availability(status, used, quantity):
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_sscc', return_value=bucket(status)), patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_active_or_completed_by_code') as by_code:
        result = ScannerResolutionService.lookup_by_location('MAL04OLD', 'AGRO')
        assert result['is_used_up'] is used
        assert result['stan_magazynowy'] == quantity
        assert result['can_dispatch'] is not used
        by_code.assert_not_called()


def test_unknown_label_does_not_resolve_fresh_bucket():
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_sscc', return_value=None), patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_active_or_completed_by_code', return_value=bucket('skompletowane')) as by_code:
        assert ScannerResolutionService.lookup_by_location('MAL04UNKNOWN', 'AGRO') is None
        by_code.assert_not_called()


@pytest.mark.parametrize('code', ['V1', 'V01', 'W01', 'WIADRO_01'])
def test_physical_bucket_without_active_filling_is_free_not_last_consumed(code):
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_active_or_completed_by_code', return_value=None), patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_latest_by_code', return_value=bucket()) as history:
        result = ScannerResolutionService.lookup_by_location(code, 'AGRO')
    assert result['is_free'] is True
    assert result['status'] == 'wolne'
    assert result['is_used_up'] is False
    assert result['pozycje'] == []
    assert result['plan_id'] is None
    assert result['can_dispatch'] is False
    history.assert_not_called()


def test_physical_bucket_resolves_current_ready_filling():
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_active_or_completed_by_code', return_value=bucket('skompletowane')):
        result = ScannerResolutionService.lookup_by_location('V4', 'AGRO')
    assert result['status'] == 'skompletowane'
    assert result['bucket_label'] == 'MAL04OLD'
    assert result['can_dispatch'] is True


def test_old_filling_label_cannot_open_new_weighing():
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_sscc', return_value=bucket()), patch(
            'app.services.bucket_maluch_service.get_db_connection') as connection:
        assert BucketMaluchService.start_bucket('MAL04OLD', 123, 'AGRO')[0] is False
    connection.assert_not_called()


@pytest.mark.parametrize('code', ['KO01', 'PAL1', 'V100', 'unknown1'])
def test_other_scans_are_not_physical_bucket_codes(code):
    assert BucketMaluchService.normalize_bucket_code(code) == ''


def test_consumed_label_cannot_dump_new_filling():
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_sscc', return_value=bucket()), patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_active_or_completed_by_code', return_value=bucket('skompletowane')) as by_code, patch(
            'app.services.bucket_maluch_service.get_db_connection') as connection:
        assert not BucketMaluchService.scan_and_dump_to_mixer('MAL04OLD', 123, 456, linia='AGRO')[0]
        by_code.assert_not_called()
        connection.assert_not_called()


def test_failed_status_update_is_not_reported_as_consumed():
    connection = MagicMock()
    connection.cursor.return_value.fetchone.side_effect = [
        {'id': 123, 'produkt': 'TEST', 'status': 'w toku', 'sekcja': 'Zasyp'},
        {'id': 456, 'nr_szarzy': 1}, None]
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_sscc', return_value=bucket('skompletowane')), patch(
            'app.services.bucket_maluch_service.get_db_connection', return_value=connection), patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.dump_bucket_to_mixer', return_value=False), patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_id') as reload_bucket:
        assert not BucketMaluchService.scan_and_dump_to_mixer('MAL04OLD', 123, 456, linia='AGRO')[0]
        reload_bucket.assert_not_called()
        connection.commit.assert_not_called()


@pytest.mark.parametrize('force', [False, True])
def test_consumed_history_cannot_be_deleted(force):
    with patch('app.repositories.bucket_maluch_repository.BucketMaluchRepository.find_by_id', return_value=bucket()), patch(
            'app.repositories.bucket_maluch_repository.BucketMaluchRepository.delete_bucket') as delete:
        assert not BucketMaluchService.delete_bucket(1, 'operator', force=force)[0]
        delete.assert_not_called()


def test_consumption_between_lookup_and_delete_keeps_history():
    from app.repositories.bucket_maluch_repository import BucketMaluchRepository
    connection = MagicMock()
    connection.cursor.return_value.fetchone.return_value = ('wrzucone_do_mieszalnika',)
    with patch('app.repositories.bucket_maluch_repository.get_db_connection', return_value=connection):
        assert BucketMaluchRepository.delete_bucket(1) is False
    connection.cursor.return_value.execute.assert_called_once()
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
