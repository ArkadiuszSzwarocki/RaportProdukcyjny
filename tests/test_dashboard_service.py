"""Tests for DashboardService."""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import date, datetime, timedelta
from app.services.dashboard_service import DashboardService


class TestBasicStaffData:
    """Tests for get_basic_staff_data method."""
    
    def test_get_basic_staff_data_returns_dict(self):
        """Test that method returns dict with expected keys."""
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            mock_qh.get_pracownicy.return_value = [
                (1, 'Adam', 'Kowalski'),
                (2, 'Beata', 'Nowak'),
            ]
            mock_qh.get_obsada_zmiany.return_value = [(1,)]
            
            result = DashboardService.get_basic_staff_data(date.today())
            
            assert isinstance(result, dict)
            assert 'wszyscy' in result
            assert 'zajeci_ids' in result
            assert 'dostepni' in result
            assert 'obsada' in result
    
    def test_get_basic_staff_data_calculates_available(self):
        """Test that available staff excludes occupied."""
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            wszyscy = [(1, 'Adam', 'Kowalski'), (2, 'Beata', 'Nowak'), (3, 'Czesław', 'Lewandowski')]
            mock_qh.get_pracownicy.return_value = wszyscy
            mock_qh.get_obsada_zmiany.return_value = [(1,), (3,)]  # IDs 1 and 3 occupied
            
            result = DashboardService.get_basic_staff_data(date.today())
            
            assert len(result['dostepni']) == 1
            assert result['dostepni'][0][0] == 2  # Only Beata available
            assert len(result['zajeci_ids']) == 2


class TestJournalEntries:
    """Tests for get_journal_entries method."""
    
    def test_get_journal_entries_formats_times(self):
        """Test that times are formatted as HH:MM."""
        test_date = date.today()
        test_time = datetime.strptime('08:30:00', '%H:%M:%S').time()
        
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            # Mock journal entry: (id, section, person, time_start, time_stop)
            mock_qh.get_dziennik_zmiany.return_value = [
                [1, 'Zasyp', 'Adam', datetime.combine(test_date, test_time), None]
            ]
            
            result = DashboardService.get_journal_entries(test_date, 'Zasyp')
            
            assert result[0][3] == '08:30'
            assert result[0][4] == ''
    
    def test_get_journal_entries_handles_none_times(self):
        """Test that None times are handled gracefully."""
        test_date = date.today()
        
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            mock_qh.get_dziennik_zmiany.return_value = [
                [1, 'Zasyp', 'Adam', None, None]
            ]
            
            result = DashboardService.get_journal_entries(test_date, 'Zasyp')
            
            assert result[0][3] == ''
            assert result[0][4] == ''


class TestWarehouseData:
    """Tests for get_warehouse_data method."""
    
    def test_get_warehouse_data_returns_tuple(self):
        """Test that warehouse data returns tuple of three items."""
        test_date = date.today()
        
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            with patch('app.services.dashboard_service.PaletaDTO') as mock_dto:
                mock_qh.get_paletki_magazyn.return_value = []
                mock_qh.get_unconfirmed_paletki.return_value = []
                
                result = DashboardService.get_warehouse_data(test_date)
                
                assert len(result) == 3
                assert isinstance(result[0], list)  # magazyn_palety
                assert isinstance(result[1], list)  # unconfirmed_palety
                assert isinstance(result[2], (int, float))  # suma_wykonanie
    
    def test_get_warehouse_data_calculates_sum(self):
        """Test that warehouse data calculates sum correctly."""
        test_date = date.today()
        
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            with patch('app.services.dashboard_service.PaletaDTO') as mock_dto_class:
                # Mock palety with weights
                mock_dto1 = MagicMock()
                mock_dto1.produkt = 'Product1'
                mock_dto1.waga = 10
                mock_dto1.data_dodania = datetime.now()
                mock_dto1.id = 1
                mock_dto1.plan_id = 1
                mock_dto1.status = 'przyjeta'
                
                mock_dto2 = MagicMock()
                mock_dto2.produkt = 'Product2'
                mock_dto2.waga = 20
                mock_dto2.data_dodania = datetime.now()
                mock_dto2.id = 2
                mock_dto2.plan_id = 1
                mock_dto2.status = 'przyjeta'
                
                mock_dto_class.from_db_row.side_effect = [mock_dto1, mock_dto2]
                mock_qh.get_paletki_magazyn.return_value = [
                    (10, 'Product1', datetime.now()),
                    (20, 'Product2', datetime.now())
                ]
                mock_qh.get_unconfirmed_paletki.return_value = []
                
                result = DashboardService.get_warehouse_data(test_date)
                
                assert result[2] == 30  # Total weight


class TestProductionPlans:
    """Tests for get_production_plans method."""
    
    def test_get_production_plans_returns_tuple(self):
        """Test that production plans returns tuple of 4 items."""
        test_date = date.today()
        
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            mock_qh.get_plan_produkcji.return_value = []
            
            result = DashboardService.get_production_plans(test_date, 'Zasyp')
            
            assert len(result) == 4
            assert isinstance(result[0], list)  # plans
            assert isinstance(result[1], dict)  # palety_mapa
            assert isinstance(result[2], int)  # suma_plan
            assert isinstance(result[3], int)  # suma_wykonanie
    
    def test_get_production_plans_formats_times(self):
        """Test that plan times are formatted as HH:MM."""
        test_date = date.today()
        test_time = datetime.strptime('09:15:00', '%H:%M:%S').time()
        
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            plan_row = [
                1,  # id
                'Product',  # produkt
                100,  # tonaz
                'zaplanowane',  # status
                datetime.combine(test_date, test_time),  # real_start
                None,  # real_stop
                0,  # duration
                50,  # tonaz_rzeczywisty
                1,  # kolejnosc
                'type1',  # typ_produkcji
                'notes'  # wyjasnienie_rozbieznosci
            ]
            mock_qh.get_plan_produkcji.return_value = [plan_row]
            
            with patch.object(DashboardService, '_is_quality_order', return_value=False):
                result = DashboardService.get_production_plans(test_date, 'Zasyp')
                
                plans = result[0]
                assert plans[0][4] == '09:15'  # Formatted time


class TestQualityAndLeave:
    """Tests for get_quality_and_leave_requests method."""
    
    def test_get_quality_and_leave_for_lider(self):
        """Test that lider gets leave requests."""
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            mock_qh.get_pending_quality_count.return_value = 5
            mock_qh.get_pending_leave_requests.return_value = [
                (1, 'Adam', 'Kowalski', 'urlop', date(2026, 2, 10))
            ]
            
            result = DashboardService.get_quality_and_leave_requests('lider')
            
            assert result['quality_count'] == 5
            assert len(result['wnioski_pending']) == 1
    
    def test_get_quality_and_leave_for_pracownik(self):
        """Test that regular worker doesn't see leave requests."""
        with patch('app.services.dashboard_service.QueryHelper') as mock_qh:
            mock_qh.get_pending_quality_count.return_value = 0
            
            result = DashboardService.get_quality_and_leave_requests('pracownik')
            
            assert result['quality_count'] == 0
            assert result['wnioski_pending'] == []


class TestShiftNotes:
    """Tests for get_shift_notes method."""
    
    def test_get_shift_notes_returns_list(self):
        """Test that shift notes returns list of dicts."""
        with patch('app.services.dashboard_service.get_db_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [
                (1, 100, '2026-02-07', 'Test note', 'admin', datetime.now())
            ]
            mock_conn.return_value.cursor.return_value = mock_cursor
            
            result = DashboardService.get_shift_notes()
            
            assert isinstance(result, list)
            if result:  # If any notes
                assert isinstance(result[0], dict)
                assert 'id' in result[0]
                assert 'pracownik_id' in result[0]


class TestFullPlansForSections:
    """Tests for get_full_plans_for_sections method."""
    
    def test_get_full_plans_returns_tuple(self):
        """Test that method returns tuple of two lists."""
        test_date = date.today()
        
        with patch('app.services.dashboard_service.get_db_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.return_value.cursor.return_value = mock_cursor
            
            result = DashboardService.get_full_plans_for_sections(test_date)
            
            assert len(result) == 2
            assert isinstance(result[0], list)  # plans_zasyp
            assert isinstance(result[1], list)  # plans_workowanie


class TestHelperMethods:
    """Tests for helper static methods."""
    
    def test_calculate_elapsed_time(self):
        """Test elapsed time calculation."""
        past_time = datetime.now() - timedelta(minutes=5)
        elapsed = DashboardService._calculate_elapsed_time(past_time)
        
        assert '5m' in elapsed or '4m' in elapsed  # Allow 1 second variance
        assert isinstance(elapsed, str)
    
    def test_get_next_workowanie_id(self):
        """Test getting next Workowanie ID."""
        plans = [
            [1, 'Product1', 100, 'w toku', None, None, 0, 50, 1, 'type', ''],
            [2, 'Product2', 100, 'zaplanowane', None, None, 0, 0, 2, 'type', ''],
            [3, 'Product3', 100, 'zaplanowane', None, None, 0, 0, 3, 'type', ''],
        ]
        
        next_id = DashboardService.get_next_workowanie_id(plans)
        
        # Should return first zaplanowane (ID 2)
        assert next_id == 2
    
    def test_get_next_workowanie_id_no_planned(self):
        """Test getting next Workowanie ID when none planned."""
        plans = [
            [1, 'Product1', 100, 'zakonczone', None, None, 0, 50, 1, 'type', ''],
        ]
        
        next_id = DashboardService.get_next_workowanie_id(plans)
        
        assert next_id is None
