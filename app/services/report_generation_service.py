"""Report generation service: handling shift closing and report creation.

Manages:
- Closing in-progress production plans
- Recording final shift reports in database
- Generating Excel, text, and PDF reports
- Creating ZIP archives with reports
- Sending reports via Outlook (if available)
"""

from datetime import date
from typing import Tuple, Optional, Dict
from pathlib import Path
import os
from zipfile import ZipFile

from app.db import get_db_connection


class ReportGenerationService:
    """Service for handling shift closing and report generation."""

    @staticmethod
    def close_shift_and_generate_reports(uwagi_lidera: str = '') -> Tuple[Optional[Tuple], Optional[str]]:
        """Close shift and generate final reports.
        
        Performs complete shift closing workflow:
        1. Closes all in-progress production orders
        2. Records final report in database
        3. Generates Excel, text, and PDF reports
        4. Creates ZIP archive with all reports
        
        Args:
            uwagi_lidera: Leader notes/comments for the shift report
            
        Returns:
            Tuple of (file_path, mime_type) for ZIP download, or (None, None) if generation failed
        """
        # Step 1: Close orders and record report
        try:
            ReportGenerationService._close_in_progress_orders(uwagi_lidera)
        except Exception as e:
            from flask import current_app
            current_app.logger.exception('Failed to close orders: %s', e)
            return None, None
        
        # Step 2: Generate report files
        xls_path, txt_path, pdf_path = ReportGenerationService._generate_report_files()
        
        # Step 3: Try Outlook (optional, non-blocking)
        try:
            ReportGenerationService._send_to_outlook(xls_path, uwagi_lidera)
        except Exception as e:
            from flask import current_app
            current_app.logger.exception('Outlook send failed (non-blocking): %s', e)
        
        # Step 4: Create and return ZIP
        zip_path = ReportGenerationService._create_report_zip(xls_path, txt_path, pdf_path)
        if zip_path:
            return (zip_path, 'application/zip')
        
        return None, None

    @staticmethod
    def _close_in_progress_orders(uwagi_lidera: str) -> None:
        """Close all in-progress production orders and record final report.
        
        Args:
            uwagi_lidera: Leader notes for the report
            
        Raises:
            Exception: If database operations fail
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Close all in-progress orders
            cursor.execute(
                "UPDATE plan_produkcji SET status='zakonczone', real_stop=NOW() WHERE status='w toku'"
            )
            
            # Record final report
            cursor.execute(
                "INSERT INTO raporty_koncowe (data_raportu, lider_uwagi) VALUES (%s, %s)",
                (date.today(), uwagi_lidera)
            )
            
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def _generate_report_files() -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Generate Excel, text, and PDF report files.
        
        Returns:
            Tuple of (xls_path, txt_path, pdf_path) - any can be None if generation failed
        """
        # Import report generators (may not be available in test/dev environment)
        try:
            from generator_raportow import generuj_excel_zmiany
        except (ImportError, ModuleNotFoundError):
            return None, None, None
        
        xls_path = None
        txt_path = None
        pdf_path = None
        
        try:
            # Generator returns tuple of (xls, txt, pdf)
            xls_path, txt_path, pdf_path = generuj_excel_zmiany(date.today())
        except Exception as e:
            from flask import current_app
            current_app.logger.exception('Report generation failed: %s', e)
        
        return xls_path, txt_path, pdf_path

    @staticmethod
    def _create_report_zip(xls_path: Optional[str], txt_path: Optional[str], 
                          pdf_path: Optional[str]) -> Optional[str]:
        """Create ZIP archive containing generated report files.
        
        Args:
            xls_path: Path to Excel report file (can be None)
            txt_path: Path to text report file (can be None)
            pdf_path: Path to PDF report file (can be None)
            
        Returns:
            Path to created ZIP file, or None if no files to archive
        """
        # If all paths are None, nothing to archive
        if not any([xls_path, txt_path, pdf_path]):
            return None
        
        zip_name = f"Raport_{date.today()}.zip"
        raporty_dir = Path('raporty')
        raporty_dir.mkdir(exist_ok=True)
        zip_path = str(raporty_dir / zip_name)
        
        try:
            with ZipFile(zip_path, 'w') as z:
                # Add each file if it exists
                if xls_path and os.path.exists(xls_path):
                    z.write(xls_path, arcname=os.path.basename(xls_path))
                if txt_path and os.path.exists(txt_path):
                    z.write(txt_path, arcname=os.path.basename(txt_path))
                if pdf_path and os.path.exists(pdf_path):
                    z.write(pdf_path, arcname=os.path.basename(pdf_path))
            
            return zip_path
        except Exception as e:
            from flask import current_app
            current_app.logger.exception('Failed to create ZIP: %s', e)
            return None

    @staticmethod
    def _send_to_outlook(xls_path: Optional[str], uwagi_lidera: str) -> None:
        """Send report via Outlook email.
        
        Args:
            xls_path: Path to Excel report file
            uwagi_lidera: Leader notes/message body
            
        Raises:
            Exception: If Outlook sending fails
        """
        if not xls_path:
            return
        
        try:
            from generator_raportow import otworz_outlook_z_raportem
            otworz_outlook_z_raportem(xls_path, uwagi_lidera)
        except (ImportError, ModuleNotFoundError):
            # Outlook functionality not available
            pass
        except Exception as e:
            # Log but don't block - Outlook failure is non-critical
            from flask import current_app
            current_app.logger.exception('Outlook send failed: %s', e)
            raise

    @staticmethod
    def get_report_files_for_date(report_date: date) -> Dict[str, Optional[str]]:
        """Retrieve paths to generated report files for a specific date.
        
        Args:
            report_date: Date to retrieve reports for
            
        Returns:
            Dict with keys 'excel', 'text', 'pdf' pointing to file paths (or None if not found)
        """
        raporty_dir = Path('raporty')
        report_prefix = f"Raport_{report_date}"
        
        files = {
            'excel': None,
            'text': None,
            'pdf': None,
        }
        
        if not raporty_dir.exists():
            return files
        
        # Search for report files with matching date
        for file_path in raporty_dir.glob('*'):
            if str(report_date) in file_path.name:
                if file_path.suffix in ['.xlsx', '.xls']:
                    files['excel'] = str(file_path)
                elif file_path.suffix == '.txt':
                    files['text'] = str(file_path)
                elif file_path.suffix == '.pdf':
                    files['pdf'] = str(file_path)
        
        return files

    @staticmethod
    def delete_old_reports(days_keep: int = 30) -> int:
        """Delete report files older than specified days.
        
        Args:
            days_keep: Number of days to keep reports (default 30)
            
        Returns:
            Number of files deleted
        """
        from datetime import datetime, timedelta
        
        raporty_dir = Path('raporty')
        if not raporty_dir.exists():
            return 0
        
        cutoff_date = datetime.now() - timedelta(days=days_keep)
        deleted_count = 0
        
        try:
            for file_path in raporty_dir.glob('Raport_*'):
                if file_path.is_file():
                    file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                    if file_mtime < cutoff_date:
                        file_path.unlink()
                        deleted_count += 1
        except Exception as e:
            from flask import current_app
            current_app.logger.exception('Failed to delete old reports: %s', e)
        
        return deleted_count
