"""Dashboard service: data aggregation orchestrator.
Delegates heavy lifting to specialized services while maintaining backward compatibility.
"""

from datetime import date
import re
from typing import Dict, List, Tuple, Any, Optional
from app.db import get_db_connection, get_table_name
from app.services.staff_service import StaffService
from app.services.production_service import ProductionService
from app.services.warehouse_service import WarehouseService
from app.services.hr_service import HRService
from app.utils.queries import QueryHelper


def _extract_bag_kg(value):
    """Extract bag weight (kg) from values like 'worki_zgrzewane_20'."""
    if value is None:
        return None

    match = re.search(r"(\d+(?:[\.,]\d+)?)", str(value))
    if not match:
        return None

    raw = match.group(1).replace(',', '.')
    try:
        kg = float(raw)
    except (TypeError, ValueError):
        return None

    return kg if kg > 0 else None


def _resolve_agro_bag_kg(cursor, active_plan, history, product_typ_cache):
    """Resolve kg/worek for AGRO context using available plan/history metadata."""
    for row in history or []:
        kg = row.get('kg_na_worek')
        if kg is None:
            continue
        try:
            kg_val = float(kg)
        except (TypeError, ValueError):
            continue
        if kg_val > 0:
            return kg_val

    for key in ('typ_produkcji', 'zasyp_typ_produkcji'):
        kg = _extract_bag_kg((active_plan or {}).get(key))
        if kg:
            return kg

    produkt = str((active_plan or {}).get('produkt') or '').strip()
    if produkt:
        if produkt not in product_typ_cache:
            cursor.execute(
                "SELECT typ_produkcji FROM produkty_receptury WHERE nazwa_produktu = %s ORDER BY id DESC LIMIT 1",
                (produkt,),
            )
            product_row = cursor.fetchone()
            if isinstance(product_row, dict):
                product_typ_cache[produkt] = product_row.get('typ_produkcji')
            else:
                product_typ_cache[produkt] = None

        kg = _extract_bag_kg(product_typ_cache.get(produkt))
        if kg:
            return kg

    if '20' in produkt.lower():
        return 20.0

    return 25.0


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
    def get_production_plans(dzisiaj: date, sekcja: str, linia='PSD', cursor=None, data_od=None, data_do=None) -> Tuple[List, Dict, int, int]:
        return ProductionService.get_production_plans(dzisiaj, sekcja, linia, cursor, data_od=data_od, data_do=data_do)

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
    def get_full_plans_for_sections(dzisiaj: date, linia='PSD', cursor=None, data_od=None, data_do=None) -> Tuple[List, List]:
        """Fetch plans for Zasyp and Workowanie (Legacy return format for compatibility)."""
        close_conn = False
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            close_conn = True
            
        plans_zasyp, _, _, _ = ProductionService.get_production_plans(dzisiaj, 'Zasyp', linia, cursor, data_od=data_od, data_do=data_do)
        plans_workowanie, _, _, _ = ProductionService.get_production_plans(dzisiaj, 'Workowanie', linia, cursor, data_od=data_od, data_do=data_do)
        
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
            f"WHERE DATE(data_planu) = %s AND sekcja IN ('Workowanie', 'Czyszczenie') "
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
    def get_active_products(dzisiaj: date, linia='PSD', cursor=None) -> dict:
        """List products that are currently in progress ('w toku'), grouped by sekcja."""
        close_conn = False
        if cursor is None:
            conn = get_db_connection()
            cursor = conn.cursor()
            close_conn = True
            
        table = get_table_name('plan_produkcji', linia)
        cursor.execute(
            f"SELECT DISTINCT sekcja, produkt FROM {table} WHERE DATE(data_planu) = %s "
            f"AND status = 'w toku' AND is_deleted = 0",
            (dzisiaj,)
        )
        
        res = {}
        for r in cursor.fetchall():
            s = r[0]
            p = r[1]
            if s not in res:
                res[s] = []
            res[s].append(p)
        
        if close_conn: conn.close()
        return res

    @staticmethod
    def get_agro_packaging_context(dzisiaj: date) -> Dict[str, Any]:
        """Fetch packaging usage context specifically for AGRO hall."""
        default_ctx = {
            'active_plan': None,
            'is_active_plan': False,
            'packaging_items': [],
            'maszyna_opakowania': [],
            'inactive_opakowania': [],
            'history': [],
            'bag_kg': 25.0,
            'palety_kg_wykonane': 0.0,
            'palety_count': 0,
            'estimated_bags': 0,
            'all_warehouse_packaging': [],
        }
        try:
            from app.services.agro_warehouse_service import AgroWarehouseService
            active_plan = AgroWarehouseService.get_active_workowanie_plan(linia='AGRO', target_date=None)
            is_active_plan = bool(active_plan)
            if not active_plan:
                # If no active plan, try to fetch the last finished plan of the day
                # to keep the settlement context visible for reports.
                finished_plans = AgroWarehouseService.get_finished_plans_of_day(linia='AGRO', target_date=dzisiaj)
                if finished_plans:
                    active_plan = finished_plans[0] # Take the most recent one
                else:
                    return dict(default_ctx)
                
            plan_id = int(active_plan['id'])
            packaging_items = AgroWarehouseService.get_all_linked_packaging(plan_id) or []
            
            history = []
            conn_hist = get_db_connection()
            try:
                cur_hist = conn_hist.cursor(dictionary=True)
                cur_hist.execute(
                    "SELECT id, opakowanie_nazwa, zuzyte_worki, stan_przed, stan_po, created_at "
                    "FROM agro_workowanie_rozliczenie "
                    "WHERE plan_id = %s ORDER BY created_at DESC LIMIT 15",
                    (plan_id,)
                )
                history = cur_hist.fetchall() or []
            except Exception as e:
                print(f"Error fetching workowanie history: {e}")
            finally:
                conn_hist.close()
            all_warehouse_packaging = AgroWarehouseService.get_packaging_inventory(linia='AGRO') or []
            
            przydzielone_opakowanie_id = active_plan.get('opakowanie_id')
            if przydzielone_opakowanie_id:
                conn_filter = get_db_connection()
                try:
                    cur_filter = conn_filter.cursor()
                    cur_filter.execute("SELECT nazwa FROM magazyn_opakowania WHERE id=%s", (przydzielone_opakowanie_id,))
                    row = cur_filter.fetchone()
                    if row and row[0]:
                        przydzielona_nazwa = row[0]
                        all_warehouse_packaging = [
                            item for item in all_warehouse_packaging 
                            if item['nazwa'] == przydzielona_nazwa and item.get('lokalizacja') != 'Maszyna'
                        ]
                except Exception as e:
                    print(f"Error filtering packaging dropdown: {e}")
                finally:
                    conn_filter.close()
            else:
                # If no specific packaging was assigned, at least filter out items already on the machine
                all_warehouse_packaging = [item for item in all_warehouse_packaging if item.get('lokalizacja') != 'Maszyna']

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
            typ_prod = active_plan.get('typ_produkcji') or ''
            kg_match = re.search(r'(\d+)', typ_prod)
            if kg_match:
                bag_kg = float(kg_match.group(1))
            else:
                # Inteligentny fallback po nazwie produktu
                produkt_nazwa = str(active_plan.get('produkt') or '').lower()
                if 'mleko' in produkt_nazwa or '20' in produkt_nazwa:
                    bag_kg = 20.0
            
            estimated_bags = int(round(palety_kg_wykonane / bag_kg)) if bag_kg > 0 else 0

            # --- Live deduction logic ---
            live_total_pulled = estimated_bags
            start_machine_counter = int(active_plan.get('start_machine_counter') or 0)
            
            try:
                from app.services.mqtt_service import get_latest_data
                latest_d = get_latest_data()
                current_counter = latest_d.get('counter', 0)
                if current_counter >= start_machine_counter and start_machine_counter is not None:
                    live_total_pulled = current_counter - start_machine_counter
            except:
                pass
            
            already_logged = 0.0
            conn_loc = get_db_connection()
            try:
                cur_loc = conn_loc.cursor()
                cur_loc.execute("SELECT COALESCE(SUM(zuzyte_worki), 0) FROM agro_workowanie_rozliczenie WHERE plan_id=%s", (plan_id,))
                already_logged_row = cur_loc.fetchone()
                if already_logged_row:
                    already_logged = float(already_logged_row[0])
            except Exception:
                pass
            # ----------------------------

            maszyna_opakowania = []
            inactive_opakowania = []
            
            try:
                for item in packaging_items:
                    nazwa_itemu = item.get('nazwa') or ''
                    
                    suggested_loc = ''
                    if nazwa_itemu:
                        opak_id = item.get('opakowanie_id')
                        if opak_id:
                            table_ruch = get_table_name('magazyn_ruch', 'AGRO')
                            cur_loc.execute(
                                f"SELECT komentarz FROM {table_ruch} WHERE surowiec_id=%s AND komentarz LIKE 'Pobranie z lok:%%' ORDER BY id DESC LIMIT 1",
                                (opak_id,)
                            )
                            ruch_row = cur_loc.fetchone()
                            if ruch_row and ruch_row[0]:
                                import re
                                match = re.search(r'Pobranie z lok:\s*(.+)', ruch_row[0])
                                if match:
                                    suggested_loc = match.group(1).strip()
                        
                        if not suggested_loc:
                            cur_loc.execute(
                                "SELECT lokalizacja FROM magazyn_opakowania WHERE nazwa=%s AND lokalizacja IS NOT NULL AND lokalizacja != 'Maszyna' AND stan_magazynowy > 0 ORDER BY id DESC LIMIT 1",
                                (nazwa_itemu,)
                            )
                            loc_row = cur_loc.fetchone()
                            if loc_row and loc_row[0]:
                                suggested_loc = loc_row[0]
                            
                    p_item = {
                        'link_id': item.get('link_id'),
                        'opakowanie_id': item.get('opakowanie_id'),
                        'nazwa': nazwa_itemu,
                        'stan_poczatkowy': float(item.get('stan_poczatkowy') or 0),
                        'stan_koncowy': float(item.get('stan_koncowy') or 0) if item.get('stan_koncowy') is not None else None,
                        'is_active': bool(item.get('is_active')),
                        'stan_magazynowy': float(item.get('current_stan') or 0),
                        'suggested_loc': suggested_loc,
                    }
                    if p_item['is_active']:
                        live_usage_for_roll = max(live_total_pulled - already_logged, 0)
                        p_item['stan_magazynowy'] = p_item['stan_poczatkowy'] - live_usage_for_roll
                        p_item['live_zuzyte'] = live_usage_for_roll
                        maszyna_opakowania.append(p_item)
                    else:
                        inactive_opakowania.append(p_item)
            except Exception as e:
                print(f"Error resolving suggested locs: {e}")
            finally:
                conn_loc.close()
            
            return {
                'active_plan': active_plan,
                'is_active_plan': is_active_plan,
                'packaging_items': packaging_items,
                'maszyna_opakowania': maszyna_opakowania,
                'inactive_opakowania': inactive_opakowania,
                'history': history,
                'bag_kg': bag_kg,
                'palety_kg_wykonane': palety_kg_wykonane,
                'palety_count': palety_count,
                'estimated_bags': estimated_bags,
                'already_logged': already_logged,
                'all_warehouse_packaging': all_warehouse_packaging,
            }
        except Exception as error:
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
