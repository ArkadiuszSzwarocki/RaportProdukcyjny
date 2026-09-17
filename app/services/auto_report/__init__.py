"""
Pakiet usług automatycznego raportowania zmian produkcyjnych.
"""
from app.services.auto_report.auto_report_config_service import AutoReportConfigService
from app.services.auto_report.auto_report_schedule_service import AutoReportScheduleService
from app.services.auto_report.auto_report_history_service import AutoReportHistoryService
from app.services.auto_report.auto_report_activity_detector import AutoReportActivityDetector
from app.services.auto_report.auto_report_recipients_service import AutoReportRecipientsService
from app.services.auto_report.auto_report_dispatcher_service import AutoReportDispatcherService

__all__ = [
    'AutoReportConfigService',
    'AutoReportScheduleService',
    'AutoReportHistoryService',
    'AutoReportActivityDetector',
    'AutoReportRecipientsService',
    'AutoReportDispatcherService'
]
