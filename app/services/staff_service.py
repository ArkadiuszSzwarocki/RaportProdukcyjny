"""Staff management service.
Provides basic worker data and hall-specific assignments.
"""
from datetime import date
from typing import Dict, List, Tuple, Any, Optional
from app.db import get_db_connection, get_table_name
from app.utils.queries import QueryHelper

class StaffService:
    @staticmethod
    def get_basic_staff_data(dzisiaj: date, linia='PSD', cursor=None) -> Dict[str, Any]:
        """Get basic staff assignments and availability for a given day."""
        wszyscy = QueryHelper.get_pracownicy(cursor=cursor)
        zajeci_ids = [r[0] for r in QueryHelper.get_obsada_zmiany(dzisiaj, linia=linia, cursor=cursor)]
        dostepni = [p for p in wszyscy if p[0] not in zajeci_ids]
        obsada = QueryHelper.get_obsada_zmiany(dzisiaj, linia=linia, cursor=cursor)
        
        return {
            'wszyscy': wszyscy,
            'zajeci_ids': set(zajeci_ids),
            'dostepni': dostepni,
            'obsada': obsada,
        }

    @staticmethod
    def get_obsada_for_date(data_wpisu: date, linia='PSD') -> Dict[str, List]:
        """Get staff assignment (obsada) for a specific date/line, grouped by sekcja."""
        return QueryHelper.get_obsada_for_date(data_wpisu, linia=linia)

    @staticmethod
    def get_unassigned_pracownicy(data_wpisu: date, linia='PSD') -> List[Tuple]:
        """Get workers not assigned to any sekcja on a specific date/line."""
        return QueryHelper.get_unassigned_pracownicy(data_wpisu, linia=linia)
