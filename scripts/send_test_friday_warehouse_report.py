"""
Skrypt do wysyłki testowej raportu magazynowego z piątku na wskazany adres e-mail.
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.osip_report_email_service import OsipReportEmailService


def main():
    date_str = '2026-09-11'
    target_email = 'arkadiusz.szwarocki@wp.pl'
    print(f"[TEST_REPORT] Rozpoczynanie wysyłki testowej raportu z piątku ({date_str}) na adres: {target_email}...")
    service = OsipReportEmailService()
    ok, msg = service.send_daily_warehouse_summary_report(
        date_str=date_str,
        force=True,
        recipient_override=[target_email]
    )
    print(f"[TEST_REPORT] Wynik wysyłki: {ok}")
    print(f"[TEST_REPORT] Informacja: {msg}")


if __name__ == '__main__':
    main()
