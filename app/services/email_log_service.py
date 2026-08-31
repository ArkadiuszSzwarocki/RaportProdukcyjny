# File: app/services/email_log_service.py
"""
EmailLogService - Business logic service for querying and managing email history.
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import date
from app.repositories.email_log_repository import EmailLogRepository


class EmailLogService:
    """Service providing email history queries and stats."""

    @staticmethod
    def log_email_attempt(
        sender: str,
        recipients: List[str] | str,
        subject: str,
        source: str = 'Inne',
        linia: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        attachments: Optional[List[str] | str] = None
    ) -> int:
        """Records an email transmission attempt."""
        recipients_str = ", ".join(recipients) if isinstance(recipients, list) else str(recipients or '')
        
        att_str = None
        if isinstance(attachments, list):
            import os
            att_str = ", ".join(os.path.basename(p) for p in attachments if p)
        elif attachments:
            att_str = str(attachments)

        status_str = 'SUCCESS' if success else 'FAILED'

        return EmailLogRepository.create_log(
            sender=str(sender or 'system'),
            recipients=recipients_str,
            subject=str(subject or 'Raport'),
            source=str(source or 'Inne'),
            linia=str(linia).upper() if linia else None,
            status=status_str,
            error_message=str(error_message) if error_message else None,
            attachments=att_str
        )

    @staticmethod
    def get_history(
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None,
        linia: Optional[str] = None,
        search_query: Optional[str] = None,
        limit: int = 50,
        page: int = 1
    ) -> Dict[str, Any]:
        """Fetches paginated email history with filters and summary stats."""
        if not start_date and not end_date:
            start_date = str(date.today())
            end_date = str(date.today())

        offset = max(0, (page - 1) * limit)
        rows, total_count = EmailLogRepository.get_logs(
            start_date=start_date,
            end_date=end_date,
            status=status,
            linia=linia,
            search_query=search_query,
            limit=limit,
            offset=offset
        )

        daily_stats = EmailLogRepository.get_daily_stats(start_date or str(date.today()))

        return {
            'logs': rows,
            'total_count': total_count,
            'page': page,
            'limit': limit,
            'total_pages': (total_count + limit - 1) // limit if limit > 0 else 1,
            'stats': daily_stats
        }
