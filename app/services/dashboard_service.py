"""Dashboard service: data aggregation orchestrator.
Delegates heavy lifting to specialized services while maintaining backward compatibility.
"""

from datetime import date
from typing import Dict, List, Tuple, Any, Optional
from app.db import get_db_connection, get_table_name
from app.services.staff_service import StaffService
from app.services.production_service import ProductionService
from app.services.warehouse_service import WarehouseService
from app.services.hr_service import HRService
from app.utils.queries import QueryHelper

class DashboardService:
    """Orchestrator for aggregating dashboard data."""

    @staticmethod
    def get_basic_staff_data(dzisiaj: date, linia='PSD', cursor=None) -> Dict[str, Any]:
        return StaffService.get_basic_staff_data(dzisiaj, linia, cursor)

    @staticmethod
    def get_journal_entries(dzisiaj: date, sekcja: str, linia='PSD', cursor=None) -> List[List[Any]]:
        """Get and format journal entries for a section."""
        wpisy = QueryHelper.get_dziennik_zmiany(dzisiaj, sekcja, linia=linia)
        for w in wpisy:
            try:
                if len(w) > 3: w[3] = w[3].strftime('%H:%M') if hasattr(w[3], 'strftime') else str(w[3]) if w[3] else ''
                if len(w) > 4: w[4] = w[4].strftime('%H:%M') if hasattr(w[4], 'strftime') else str(w[4]) if w[4] else ''
            except Exception: pass
        return wpisy

    @staticmethod
    def get_warehouse_data(dzisiaj: date, linia='PSD', cursor=None) -> Tuple[List[Tuple], List[Tuple], int]:
        return WarehouseService.get_warehouse_data(dzisiaj, linia, cursor)

    @staticmethod
    def get_production_plans(dzisiaj: date, sekcja: str, linia='PSD', cursor=None) -> Tuple[List, Dict, int, int]:
        return ProductionService.get_production_plans(dzisiaj, sekcja, linia, cursor)

    @staticmethod
    def get_hr_and_leave_data(dzisiaj: date, cursor=None) -> Dict[str, Any]:
        """Fetch all HR-related data for the dashboard."""
        hr_data_raw, wnioski = HRService.get_hr_and_leave_data(dzisiaj, cursor)
        
        # Aggregate all HR data into the format expected by routes_main.py
        staff_global = StaffService.get_basic_staff_data(dzisiaj, cursor=cursor)
        planned_leaves = HRService.get_planned_leaves(days=60, cursor=cursor)
        recent_absences = HRService.get_recent_absences(days=30, cursor=cursor)
        
        return {
            'hr_pracownicy': staff_global['wszyscy'],
            'hr_dostepni': staff_global['dostepni'],
            'raporty_hr': hr_data_raw,
            'wnioski_pending': wnioski,
            'planned_leaves': planned_leaves,
            'recent_absences': recent_absences
        }

    @staticmethod
    def get_quality_and_leave_requests(rola: str, linia='PSD', cursor=None) -> Dict[str, Any]:
        """Backward compatible return for quality and leave requests."""
        q_count = ProductionService.get_pending_quality_count(linia, cursor=cursor)
        wnioski = []
        if rola in ['admin', 'lider', 'masteradmin']:
            wnioski = QueryHelper.get_pending_leave_requests(limit=10)
        
        return {
            'quality_count': q_count,
            'wnioski_pending': wnioski
        }

    @staticmethod
    def get_shift_notes(dzisiaj: date, linia='PSD', cursor=None) -> List[Dict]:
        """Fetch notes from the end of shift report (Returns list for compatibility)."""
        close_conn = False
        if cursor is None:
            try:
                from app.db import get_db_connection
                conn = get_db_connection()
                cursor = conn.cursor()
                close_conn = True
            except Exception:
                return []
        
        try:
            cursor.execute("""
                SELECT r.id, r.pracownik_id, r.data_raportu, r.lider_uwagi, p.imie_nazwisko, r.created_at 
                FROM raporty_koncowe r
                LEFT JOIN pracownicy p ON r.lider_id = p.id
                WHERE r.data_raportu = %s AND r.linia = %s
            """, (dzisiaj, linia))
            rows = cursor.fetchall()
            res = [{
                'id': r[0], 'pracownik_id': r[1], 'data_raportu': r[2], 
                'uwagi': r[3], 'user_login': r[4], 'timestamp': r[5]
            } for r in rows]
            
            if close_conn: conn.close()
            return res
        except Exception:
            if close_conn:
                try: conn.close()
                except Exception: pass
            return []

    @staticmethod
    def get_full_plans_for_sections(dzisiaj: date, linia='PSD', cursor=None) -> Tuple[List, List]:
        """Fetch plans for Zasyp and Workowanie (Legacy return format for compatibility)."""
        close_conn = False
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            close_conn = True
            
        plans_zasyp, _, _, _ = ProductionService.get_production_plans(dzisiaj, 'Zasyp', linia, cursor)
        plans_workowanie, _, _, _ = ProductionService.get_production_plans(dzisiaj, 'Workowanie', linia, cursor)
        
        if close_conn:
            conn.close()
        return plans_zasyp, plans_workowanie

    @staticmethod
    def get_zasyp_started_products(dzisiaj: date, linia='PSD', cursor=None) -> List[str]:
        """Proxy for get_zasyp_started_produkty with English name compatibility."""
        return ProductionService.get_zasyp_started_produkty(dzisiaj, linia, cursor)

    @staticmethod
    def any_plan_in_progress(dzisiaj: date, linia='PSD', cursor=None) -> bool:
        """Check if any production plan is currently 'w toku'."""
        close_conn = False
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            close_conn = True
            
        table = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT 1 FROM {table} WHERE DATE(data_planu) = %s AND status = 'w toku' AND is_deleted = 0 LIMIT 1",
            (dzisiaj,)
        )
        res = bool(cursor.fetchone())
        
        if close_conn: conn.close()
        return res

    @staticmethod
    def get_buffer_queue(dzisiaj: date, linia='PSD', cursor=None) -> Dict[str, float]:
        """Fetch current buffer state for products."""
        close_conn = False
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            close_conn = True
            
        table = get_table_name('bufor', linia)
        cursor.execute(
            f"SELECT produkt, SUM(COALESCE(tonaz_rzeczywisty, 0) - COALESCE(spakowano, 0)) "
            f"FROM {table} WHERE DATE(data_planu) = %s AND status = 'aktywny' GROUP BY produkt",
            (dzisiaj,)
        )
        res = {r[0]: float(r[1] or 0) for r in cursor.fetchall()}
        
        if close_conn: conn.close()
        return res

    @staticmethod
    def get_first_workowanie_map(dzisiaj: date, linia='PSD', cursor=None) -> Dict[str, int]:
        """Map of product name to the ID of the first Workowanie plan."""
        close_conn = False
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            close_conn = True
            
        table = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT produkt, MIN(id) FROM {table} "
            f"WHERE DATE(data_planu) = %s AND sekcja = 'Workowanie' "
            f"AND status IN ('zaplanowane', 'w toku') AND is_deleted = 0 GROUP BY produkt",
            (dzisiaj,)
        )
        res = {r[0]: r[1] for r in cursor.fetchall()}
        
        if close_conn: conn.close()
        return res

    @staticmethod
    def get_zasyp_product_order(dzisiaj: date, linia='PSD', cursor=None) -> List[str]:
        """Get the sequence of products in Zasyp section."""
        close_conn = False
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            close_conn = True
            
        table = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT DISTINCT produkt FROM {table} "
            f"WHERE DATE(data_planu) = %s AND sekcja = 'Zasyp' AND is_deleted = 0 "
            "ORDER BY kolejnosc ASC, id ASC",
            (dzisiaj,)
        )
        res = [r[0] for r in cursor.fetchall()]
        
        if close_conn: conn.close()
        return res

    @staticmethod
    def get_zasyp_active_status(dzisiaj: date, linia='PSD', cursor=None) -> bool:
        """Check if any Zasyp plan is currently active."""
        close_conn = False
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            close_conn = True
            
        table = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT 1 FROM {table} WHERE DATE(data_planu) = %s AND sekcja = 'Zasyp' "
            f"AND status = 'w toku' AND is_deleted = 0 LIMIT 1",
            (dzisiaj,)
        )
        res = bool(cursor.fetchone())
        
        if close_conn: conn.close()
        return res

    @staticmethod
    def get_active_products(dzisiaj: date, linia='PSD', cursor=None) -> List[str]:
        """List products that are currently in progress ('w toku')."""
        close_conn = False
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            close_conn = True
            
        table = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT DISTINCT produkt FROM {table} WHERE DATE(data_planu) = %s "
            f"AND status = 'w toku' AND is_deleted = 0",
            (dzisiaj,)
        )
        res = [r[0] for r in cursor.fetchall()]
        
        if close_conn: conn.close()
        return res

    @staticmethod
    def get_agro_packaging_context(dzisiaj: date) -> Dict[str, Any]:
        """Fetch packaging usage context specifically for AGRO hall."""
        default_ctx = {
            'active_plan': None,
            'packaging_items': [],
            'maszyna_opakowania': [],
            'history': [],
            'bag_kg': 25.0,
            'palety_kg_wykonane': 0.0,
            'palety_count': 0,
            'estimated_bags': 0,
            'available_packaging': [],
            'all_linked_packaging': [],
            'total_actual_consumed': 0.0,
            'straty_workow': 0.0,
        }
        try:
            from app.services.agro_warehouse_service import AgroWarehouseService
            active_plan = AgroWarehouseService.get_active_workowanie_plan(linia='AGRO', target_date=dzisiaj)
            if not active_plan:
                # If no active plan, try to fetch the last finished plan of the day
                # to keep the settlement context visible for reports.
                finished_plans = AgroWarehouseService.get_finished_plans_of_day(linia='AGRO', target_date=dzisiaj)
                if finished_plans:
                    active_plan = finished_plans[0] # Take the most recent one
                else:
                    return dict(default_ctx)
                
            plan_id = int(active_plan['id'])
            packaging_items = AgroWarehouseService.get_linked_packaging(plan_id) or []
            all_linked_packaging = AgroWarehouseService.get_all_linked_packaging(plan_id) or []
            available_packaging = AgroWarehouseService.get_available_packaging_for_linking(plan_id) or []
            history = AgroWarehouseService.get_history(limit=10, plan_id=plan_id, linia='AGRO') or []

            table_palety = get_table_name('palety_workowanie', 'AGRO')
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"SELECT COUNT(*), COALESCE(SUM(waga), 0) FROM {table_palety} WHERE plan_id=%s",
                    (plan_id,),
                )
                totals_row = cursor.fetchone() or (0, 0)
            finally:
                try:
                    conn.close()
                except Exception:
                    pass

            palety_count = int(totals_row[0] or 0)
            palety_kg_wykonane = float(totals_row[1] or 0.0)
            
            # Determine bag weight from typ_produkcji (e.g. 'worki_zgrzewane_25' -> 25)
            import re
            bag_kg = 25.0
            typ_prod = (active_plan.get('typ_produkcji') or '').strip().lower()
            if typ_prod == 'agro':
                bag_kg = 20.0
            else:
                kg_match = re.search(r'(\d+)', typ_prod)
                if kg_match:
                    bag_kg = float(kg_match.group(1))
            
            estimated_bags = int(round(palety_kg_wykonane / bag_kg)) if bag_kg > 0 else 0

            maszyna_opakowania = []
            for item in packaging_items:
                maszyna_opakowania.append(
                    {
                        'id': item.get('opakowanie_id'),
                        'nazwa': item.get('nazwa') or '',
                        'stan_magazynowy': float(item.get('current_stan') or 0),
                        'is_linked': bool(item.get('is_active')),
                    }
                )
            
            total_actual_consumed = 0.0
            for item in all_linked_packaging:
                stan_przed = float(item.get('stan_poczatkowy') or 0.0)
                if item.get('is_active'):
                    total_actual_consumed += stan_przed
                else:
                    stan_po = float(item.get('stan_koncowy') or 0.0) if item.get('stan_koncowy') is not None else 0.0
                    total_actual_consumed += max(stan_przed - stan_po, 0.0)
            
            straty_workow = max(total_actual_consumed - estimated_bags, 0.0)
            
            return {
                'active_plan': active_plan,
                'packaging_items': packaging_items,
                'maszyna_opakowania': maszyna_opakowania,
                'history': history,
                'bag_kg': bag_kg,
                'palety_kg_wykonane': palety_kg_wykonane,
                'palety_count': palety_count,
                'estimated_bags': estimated_bags,
                'available_packaging': available_packaging,
                'all_linked_packaging': all_linked_packaging,
                'total_actual_consumed': total_actual_consumed,
                'straty_workow': straty_workow,
            }
        except Exception as error:
            out = dict(default_ctx)
            out['wrctx_error'] = str(error)
            return out

    @staticmethod
    def _load_workowanie_rozliczenie_context(cursor, data_planu, preferred_plan_id=None) -> Dict[str, Any]:
        """Loads the settlement context for AGRO Workowanie using an existing cursor."""
        default_ctx = {
            'active_plan': None,
            'packaging_items': [],
            'maszyna_opakowania': [],
            'history': [],
            'bag_kg': 25.0,
            'palety_kg_wykonane': 0.0,
            'palety_count': 0,
            'estimated_bags': 0,
            'available_packaging': [],
            'all_linked_packaging': [],
            'total_actual_consumed': 0.0,
            'straty_workow': 0.0,
        }
        
        try:
            # 1. Fetch active plan
            active_plan = None
            table_plan = get_table_name('plan_produkcji', 'AGRO')
            
            if preferred_plan_id:
                cursor.execute(
                    f"SELECT id, produkt, data_planu, typ_produkcji, status, sugerowana_folia FROM {table_plan} WHERE id = %s",
                    (preferred_plan_id,)
                )
                active_plan = cursor.fetchone()
                
            if not active_plan:
                cursor.execute(
                    f"SELECT id, produkt, data_planu, typ_produkcji, status, sugerowana_folia FROM {table_plan} WHERE status='w toku' AND sekcja='Workowanie' AND DATE(data_planu) = %s ORDER BY real_start DESC LIMIT 1",
                    (data_planu,)
                )
                active_plan = cursor.fetchone()
                
            if not active_plan:
                cursor.execute(
                    f"SELECT id, produkt, data_planu, typ_produkcji, status, sugerowana_folia FROM {table_plan} WHERE status='zakonczone' AND sekcja='Workowanie' AND DATE(data_planu) = %s ORDER BY real_stop DESC LIMIT 1",
                    (data_planu,)
                )
                active_plan = cursor.fetchone()
                
            if not active_plan:
                return default_ctx

            plan_id = int(active_plan['id'])
            
            # 2. Get linked packaging (active only)
            cursor.execute("""
                SELECT ap.id as link_id, ap.opakowanie_id, ap.stan_poczatkowy, ap.stan_koncowy, ap.is_active,
                       o.nazwa, o.stan_magazynowy as current_stan
                FROM agro_plan_opakowania ap
                JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                WHERE ap.plan_id = %s AND ap.is_active = TRUE
                ORDER BY ap.created_at ASC
            """, (plan_id,))
            packaging_items = cursor.fetchall() or []
            
            # 2b. Get all linked packaging
            cursor.execute("""
                SELECT ap.id as link_id, ap.opakowanie_id, ap.stan_poczatkowy, ap.stan_koncowy, ap.is_active,
                       o.nazwa, o.stan_magazynowy as current_stan
                FROM agro_plan_opakowania ap
                JOIN magazyn_opakowania o ON ap.opakowanie_id = o.id
                WHERE ap.plan_id = %s
                ORDER BY ap.created_at ASC
            """, (plan_id,))
            all_linked_packaging = cursor.fetchall() or []
            
            # 2c. Get available warehouse packaging
            cursor.execute("""
                SELECT id, nazwa, stan_magazynowy, lokalizacja
                FROM magazyn_opakowania
                WHERE stan_magazynowy > 0
                  AND id IN (
                      SELECT opakowanie_id
                      FROM agro_plan_opakowania
                      WHERE plan_id = %s
                  )
                ORDER BY nazwa ASC
            """, (plan_id,))
            available_packaging = cursor.fetchall() or []
            
            # 3. Get history
            cursor.execute("""
                SELECT r.*, COALESCE(o.nazwa, r.opakowanie_nazwa) AS opakowanie_biezace
                FROM agro_workowanie_rozliczenie r
                LEFT JOIN magazyn_opakowania o ON o.id = r.opakowanie_id
                WHERE r.plan_id = %s
                ORDER BY r.created_at DESC LIMIT 10
            """, (plan_id,))
            history = cursor.fetchall() or []

            # 4. Get palety totals
            table_palety = get_table_name('palety_workowanie', 'AGRO')
            cursor.execute(
                f"SELECT COUNT(*), COALESCE(SUM(waga), 0) FROM {table_palety} WHERE plan_id=%s",
                (plan_id,),
            )
            totals_row = cursor.fetchone() or (0, 0)
            
            if isinstance(totals_row, dict):
                vals = list(totals_row.values())
                palety_count = int(vals[0] or 0)
                palety_kg_wykonane = float(vals[1] or 0.0)
            else:
                palety_count = int(totals_row[0] or 0)
                palety_kg_wykonane = float(totals_row[1] or 0.0)
            
            # Determine bag weight from typ_produkcji (e.g. 'worki_zgrzewane_25' -> 25)
            import re
            bag_kg = 25.0
            typ_prod = (active_plan.get('typ_produkcji') or '').strip().lower()
            if typ_prod == 'agro':
                bag_kg = 20.0
            else:
                kg_match = re.search(r'(\d+)', typ_prod)
                if kg_match:
                    bag_kg = float(kg_match.group(1))
            
            estimated_bags = int(round(palety_kg_wykonane / bag_kg)) if bag_kg > 0 else 0

            maszyna_opakowania = []
            for item in packaging_items:
                maszyna_opakowania.append(
                    {
                        'id': item.get('opakowanie_id'),
                        'nazwa': item.get('nazwa') or '',
                        'stan_magazynowy': float(item.get('current_stan') or 0),
                        'is_linked': bool(item.get('is_active')),
                    }
                )
            
            total_actual_consumed = 0.0
            for item in all_linked_packaging:
                stan_przed = float(item.get('stan_poczatkowy') or 0.0)
                if item.get('is_active'):
                    total_actual_consumed += stan_przed
                else:
                    stan_po = float(item.get('stan_koncowy') or 0.0) if item.get('stan_koncowy') is not None else 0.0
                    total_actual_consumed += max(stan_przed - stan_po, 0.0)
            
            straty_workow = max(total_actual_consumed - estimated_bags, 0.0)
            
            return {
                'active_plan': active_plan,
                'packaging_items': packaging_items,
                'maszyna_opakowania': maszyna_opakowania,
                'history': history,
                'bag_kg': bag_kg,
                'palety_kg_wykonane': palety_kg_wykonane,
                'palety_count': palety_count,
                'estimated_bags': estimated_bags,
                'available_packaging': available_packaging,
                'all_linked_packaging': all_linked_packaging,
                'total_actual_consumed': total_actual_consumed,
                'straty_workow': straty_workow,
            }
            
        except Exception as error:
            import traceback
            from flask import current_app
            try:
                current_app.logger.error(f"Error in _load_workowanie_rozliczenie_context: {error}\n{traceback.format_exc()}")
            except Exception:
                pass
            out = dict(default_ctx)
            out['wrctx_error'] = str(error)
            return out


    @staticmethod
    def _calculate_elapsed_time(dt: Any) -> str:
        """Alias for WarehouseService method (for compatibility)."""
        return WarehouseService.calculate_elapsed_time(dt)

    @staticmethod
    def get_next_workowanie_id(plans: List) -> Optional[int]:
        """Return the ID of the first 'zaplanowane' plan in the list."""
        for p in plans:
            if len(p) > 3 and p[3] == 'zaplanowane':
                return p[0]
        return None

    @staticmethod
    def _is_quality_order(plan_id: int, linia='PSD', cursor=None) -> bool:
        """Mock/Proxy for quality order check."""
        return ProductionService.get_pending_quality_count(linia, cursor) > 0 # Simplified check for compatibility
