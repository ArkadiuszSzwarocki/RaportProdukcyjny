"""Tests for ReportGenerationService."""

import pytest
from unittest.mock import MagicMock, patch, call
from datetime import date, datetime, timedelta
from pathlib import Path
import tempfile
import os
from app.services.report_generation_service import ReportGenerationService


class TestCloseShiftAndGenerateReports:
    """Tests for close_shift_and_generate_reports method."""
    
    def test_close_shift_returns_tuple(self):
        """Test that method returns tuple of (path, mime_type)."""
        with patch.object(ReportGenerationService, '_close_in_progress_orders'):
            with patch.object(ReportGenerationService, '_generate_report_files', return_value=(None, None, None)):
                with patch.object(ReportGenerationService, '_create_report_zip', return_value=None):
                    result = ReportGenerationService.close_shift_and_generate_reports()
                    
                    assert isinstance(result, tuple)
                    assert len(result) == 2
                    assert result[0] is None
                    assert result[1] is None
    
    def test_close_shift_with_uwagi(self):
        """Test that leader notes are passed to close_in_progress_orders."""
        with patch.object(ReportGenerationService, '_close_in_progress_orders') as mock_close:
            with patch.object(ReportGenerationService, '_generate_report_files', return_value=(None, None, None)):
                with patch.object(ReportGenerationService, '_create_report_zip', return_value=None):
                    with patch.object(ReportGenerationService, '_send_to_outlook'):
                        ReportGenerationService.close_shift_and_generate_reports('Test notes')
                        
                        mock_close.assert_called_once_with('Test notes')
    
    def test_close_shift_generates_reports(self):
        """Test that reports are generated."""
        with patch.object(ReportGenerationService, '_close_in_progress_orders'):
            with patch.object(ReportGenerationService, '_generate_report_files', return_value=('test.xlsx', 'test.txt', 'test.pdf')) as mock_gen:
                with patch.object(ReportGenerationService, '_create_report_zip', return_value='/path/to/report.zip'):
                    with patch.object(ReportGenerationService, '_send_to_outlook'):
                        result = ReportGenerationService.close_shift_and_generate_reports()
                        
                        mock_gen.assert_called_once()
                        assert result[0] == '/path/to/report.zip'
                        assert result[1] == 'application/zip'
    
    def test_close_shift_handles_failures_gracefully(self, app):
        """Test that method returns (None, None) on failure."""
        with patch.object(ReportGenerationService, '_close_in_progress_orders', side_effect=Exception('DB error')):
            with app.app_context():
                result = ReportGenerationService.close_shift_and_generate_reports()
                
                assert result == (None, None)


class TestCloseInProgressOrders:
    """Tests for _close_in_progress_orders method."""
    
    def test_close_orders_updates_database(self):
        """Test that in-progress orders are closed."""
        with patch('app.services.report_generation_service.get_db_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn.return_value.cursor.return_value = mock_cursor
            
            ReportGenerationService._close_in_progress_orders('Test notes')
            
            # Verify UPDATE and INSERT calls
            assert mock_cursor.execute.call_count >= 2
            # Check first execute (UPDATE)
            first_call = mock_cursor.execute.call_args_list[0]
            assert 'UPDATE plan_produkcji' in first_call[0][0]
            # Check second execute (INSERT)
            second_call = mock_cursor.execute.call_args_list[1]
            assert 'INSERT INTO raporty_koncowe' in second_call[0][0]
    
    def test_close_orders_commits_transaction(self):
        """Test that transaction is committed."""
        with patch('app.services.report_generation_service.get_db_connection') as mock_conn:
            mock_cursor = MagicMock()
            mock_conn_instance = MagicMock()
            mock_conn_instance.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_conn_instance
            
            ReportGenerationService._close_in_progress_orders('Test notes')
            
            mock_conn_instance.commit.assert_called_once()
            mock_conn_instance.close.assert_called_once()


class TestGenerateReportFiles:
    """Tests for _generate_report_files method.
    
    Note: Since generuj_excel_zmiany is conditionally imported inside the method
    and is optional (may not exist), we only test that the method returns
    proper tuple structure. Real file generation testing is done at integration level.
    """
    
    def test_generate_reports_returns_tuple(self):
        """Test that method returns tuple of 3 elements (xls, txt, pdf)."""
        # The method safely handles missing generator_raportow module
        result = ReportGenerationService._generate_report_files()
        
        assert isinstance(result, tuple)
        assert len(result) == 3


class TestCreateReportZip:
    """Tests for _create_report_zip method."""
    
    def test_create_zip_with_all_files(self):
        """Test ZIP creation with all report files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create temp files
            xls_path = os.path.join(tmpdir, 'report.xlsx')
            txt_path = os.path.join(tmpdir, 'report.txt')
            pdf_path = os.path.join(tmpdir, 'report.pdf')
            
            Path(xls_path).write_text('xls content')
            Path(txt_path).write_text('txt content')
            Path(pdf_path).write_text('pdf content')
            
            with patch('app.services.report_generation_service.ZipFile') as mock_zip:
                mock_zip_instance = MagicMock()
                mock_zip.return_value = mock_zip_instance
                mock_zip_instance.__enter__.return_value = mock_zip_instance
                
                result = ReportGenerationService._create_report_zip(xls_path, txt_path, pdf_path)
                
                # Verify ZIP was created
                assert mock_zip.called
                assert mock_zip_instance.write.call_count >= 2
    
    def test_create_zip_with_no_files(self):
        """Test that (None, None, None) returns None."""
        result = ReportGenerationService._create_report_zip(None, None, None)
        
        assert result is None
    
    def test_create_zip_with_partial_files(self):
        """Test ZIP creation with only some files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            xls_path = os.path.join(tmpdir, 'report.xlsx')
            Path(xls_path).write_text('xls content')
            
            with patch('app.services.report_generation_service.ZipFile') as mock_zip:
                mock_zip_instance = MagicMock()
                mock_zip.return_value = mock_zip_instance
                mock_zip_instance.__enter__.return_value = mock_zip_instance
                
                result = ReportGenerationService._create_report_zip(xls_path, None, None)
                
                # ZIP should still be created with available files
                assert mock_zip.called


class TestSendToOutlook:
    """Tests for _send_to_outlook method.
    
    Note: Since otworz_outlook_z_raportem is conditionally imported and optional,
    we only test error handling. Real Outlook sending is tested at integration level.
    """
    
    def test_send_to_outlook_handles_missing_module(self):
        """Test that missing generator_raportow module is handled."""
        # Should not raise exception when module missing
        try:
            ReportGenerationService._send_to_outlook('/path/to/report.xlsx', 'Test notes')
        except Exception:
            pytest.fail("_send_to_outlook raised exception with missing module")
    
    def test_send_to_outlook_handles_none_file(self):
        """Test that None file path is handled."""
        # Should not raise exception with None path
        try:
            ReportGenerationService._send_to_outlook(None, 'Test notes')
        except Exception:
            pytest.fail("_send_to_outlook raised exception with None path")


class TestGetReportFilesForDate:
    """Tests for get_report_files_for_date method."""
    
    def test_get_report_files_returns_dict(self):
        """Test that method returns dict with expected keys."""
        report_date = date.today()
        
        result = ReportGenerationService.get_report_files_for_date(report_date)
        
        assert isinstance(result, dict)
        assert 'excel' in result or 'text' in result or 'pdf' in result
    
    def test_get_report_files_no_directory(self):
        """Test behavior when raporty directory doesn't exist."""
        with patch('pathlib.Path.exists', return_value=False):
            report_date = date.today()
            
            result = ReportGenerationService.get_report_files_for_date(report_date)
            
            assert isinstance(result, dict)


class TestDeleteOldReports:
    """Tests for delete_old_reports method."""
    
    def test_delete_old_reports_returns_count(self):
        """Test that method returns count of deleted files."""
        with patch('pathlib.Path.glob', return_value=[]):
            result = ReportGenerationService.delete_old_reports(days_keep=30)
            
            assert isinstance(result, int)
            assert result >= 0
    
    def test_delete_old_reports_no_directory(self):
        """Test behavior when raporty directory doesn't exist."""
        with patch('pathlib.Path.exists', return_value=False):
            result = ReportGenerationService.delete_old_reports(days_keep=30)
            
            assert result == 0
