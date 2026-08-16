"""
Wersja: 1.1.0
Opis: Serwis HR. Obsługuje dane o obecnościach i wnioskach urlopowych.
"""
from datetime import date
from typing import Dict, List, Tuple, Any, Optional
from app.db import get_db_connection, get_table_name
from app.utils.queries import QueryHelper

class HRService:
    @staticmethod
    def get_hr_and_leave_data(dzisiaj: date, cursor=None) -> Tuple[List, List]:
        """Get HR related data: presence records and pending leave requests."""
        obecnosc_dzis = QueryHelper.get_presence_records_for_day(dzisiaj, cursor=cursor)
        wnioski_pending = QueryHelper.get_pending_leave_requests(limit=10)
        return obecnosc_dzis, wnioski_pending

    @staticmethod
    def get_planned_leaves(days=60, limit=500, cursor=None) -> List[Dict]:
        """Get planned/scheduled leaves for the next N days."""
        return QueryHelper.get_planned_leaves(days=days, limit=limit, cursor=cursor)

    @staticmethod
    def get_recent_absences(days=30, limit=500, cursor=None) -> List[Dict]:
        """Get recent absence records."""
        return QueryHelper.get_recent_absences(days=days, limit=limit, cursor=cursor)
