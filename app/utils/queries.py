"""
Wersja: 1.1.0
Opis: Centralna obsługa zapytań SQL. Zmodularyzowana dla lepszej czytelności (HR, produkcja, kadry, magazyn).
"""

from app.utils.queries_split.staff import StaffQueries
from app.utils.queries_split.production import ProductionQueries
from app.utils.queries_split.hr import HRQueries
from app.utils.queries_split.warehouse import WarehouseQueries

class QueryHelper(StaffQueries, ProductionQueries, HRQueries, WarehouseQueries):
    """Aggregated QueryHelper for backward compatibility."""
    pass
