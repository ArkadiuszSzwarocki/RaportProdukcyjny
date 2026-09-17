"""
Moduł odpowiedzialny za dokładne wyznaczanie statusów dokumentów i pozycji magazynowych.
Zapobiega oznaczaniu nieprzyjętych lub oczekujących pozycji jako zakończone.
"""
from typing import Dict, Any, List, Optional


class WarehouseStatusResolver:
    @staticmethod
    def resolve_item_status(item: Dict[str, Any], doc_status: Optional[str] = None) -> Dict[str, Any]:
        """
        Zwraca ustrukturyzowany status pozycji na podstawie jej flag i statusu dokumentu.
        """
        is_accepted = bool(item.get('accepted'))
        is_rejected = bool(item.get('rejected'))
        status_raw = str(item.get('status') or '').strip().upper()

        if is_rejected or status_raw in ('ODRZUCONA', 'REJECTED', 'CANCELLED'):
            return {
                'status_code': 'REJECTED',
                'status_label': 'ODRZUCONA',
                'badge_color': '#991b1b',
                'badge_bg': '#fee2e2',
                'is_accepted': False,
                'is_pending': False
            }

        if is_accepted or status_raw in ('PRZYJĘTA', 'PRZYJETA', 'RECEIVED', 'COMPLETED'):
            return {
                'status_code': 'ACCEPTED',
                'status_label': 'PRZYJĘTA',
                'badge_color': '#166534',
                'badge_bg': '#dcfce7',
                'is_accepted': True,
                'is_pending': False
            }

        # Domyślnie dla niepotwierdzonych pozycji
        return {
            'status_code': 'PENDING',
            'status_label': 'OCZEKUJE',
            'badge_color': '#b45309',
            'badge_bg': '#fef3c7',
            'is_accepted': False,
            'is_pending': True
        }

    @staticmethod
    def resolve_document_status(doc: Dict[str, Any], items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Wyznacza rzeczywisty status całego dokumentu na podstawie bazy danych i pozycji.
        """
        db_status = str(doc.get('status') or 'OCZEKUJE').strip().upper()

        if not items:
            is_completed = db_status in ('COMPLETED', 'ZAKONCZONE', 'ZAKOŃCZONE')
            return {
                'status_code': 'COMPLETED' if is_completed else 'PENDING',
                'status_label': 'ZAKOŃCZONE (COMPLETED)' if is_completed else 'OCZEKUJE (PENDING)',
                'is_completed': is_completed
            }

        resolved_items = [WarehouseStatusResolver.resolve_item_status(it, db_status) for it in items]
        all_accepted = all(it['is_accepted'] for it in resolved_items)
        any_pending = any(it['is_pending'] for it in resolved_items)

        if db_status in ('COMPLETED', 'ZAKONCZONE', 'ZAKOŃCZONE') and not any_pending:
            return {
                'status_code': 'COMPLETED',
                'status_label': 'ZAKOŃCZONE (COMPLETED)',
                'is_completed': True
            }

        if all_accepted:
            return {
                'status_code': 'COMPLETED',
                'status_label': 'ZAKOŃCZONE (COMPLETED)',
                'is_completed': True
            }

        return {
            'status_code': 'PENDING',
            'status_label': 'W TRAKCIE REALIZACJI / OCZEKUJE',
            'is_completed': False
        }
