"""Dashboard service: data aggregation and preparation for dashboard rendering.

Handles:
- Fetching production plans, staff assignments, warehouse inventory
- Formatting times, computing sums and differences
- Building lookup maps for UI efficiency
- Load balancing across multiple data sources
"""

from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple, Any, Optional
from app.db import get_db_connection
from app.utils.queries import QueryHelper
from app.dto.paleta import PaletaDTO


class DashboardService:
    """Service for aggregating and preparing dashboard data."""

    @staticmethod
    def get_basic_staff_data(dzisiaj: date) -> Dict[str, Any]:
        """Get basic staff assignments and availability for a given day.
        
        Returns dict with keys:
        - wszyscy: list of all staff (id, name, surname)
        - zajeci_ids: set of occupied staff IDs
        - dostepni: list of available staff
        - obsada: current shift assignments
        """
        wszyscy = QueryHelper.get_pracownicy()
        zajeci_ids = [r[0] for r in QueryHelper.get_obsada_zmiany(dzisiaj)]
        dostepni = [p for p in wszyscy if p[0] not in zajeci_ids]
        obsada = QueryHelper.get_obsada_zmiany(dzisiaj)
        
        return {
            'wszyscy': wszyscy,
            'zajeci_ids': set(zajeci_ids),
            'dostepni': dostepni,
            'obsada': obsada,
        }

    @staticmethod
    def get_journal_entries(dzisiaj: date, sekcja: str) -> List[List[Any]]:
        """Get and format journal entries for a section."""
        wpisy = QueryHelper.get_dziennik_zmiany(dzisiaj, sekcja)
        
        # Format czas_start/czas_stop as HH:MM
        for w in wpisy:
            try:
                w[3] = w[3].strftime('%H:%M') if w[3] else ''
            except Exception:
                w[3] = str(w[3]) if w[3] else ''
            try:
                w[4] = w[4].strftime('%H:%M') if w[4] else ''
            except Exception:
                w[4] = str(w[4]) if w[4] else ''
        
        return wpisy

    @staticmethod
    def get_warehouse_data(dzisiaj: date) -> Tuple[List[Tuple], List[Tuple]]:
        """Get warehouse (Magazyn) palety and unconfirmed palety."""
        raw_mag = QueryHelper.get_paletki_magazyn(dzisiaj)
        magazyn_palety = []
        suma_wykonanie = 0
        
        for r in raw_mag:
            dto = PaletaDTO.from_db_row(r)
            dt = dto.data_dodania
            try:
                sdt = dt.strftime('%H:%M') if hasattr(dt, 'strftime') else str(dt)
            except Exception:
                sdt = str(dt)
            
            # Get actual confirmation time or calculate fallback
            czas_rzeczywisty = '-'
            try:
                if len(r) > 10 and r[10]:
                    czas_obj = r[10]
                    if hasattr(czas_obj, 'strftime'):
                        czas_rzeczywisty = czas_obj.strftime('%H:%M')
                    else:
                        czas_str = str(czas_obj)
                        if ':' in czas_str:
                            parts = czas_str.split(':')
                            czas_rzeczywisty = f"{parts[0]}:{parts[1]}"
                else:
                    if dt and hasattr(dt, 'strftime'):
                        czas_oblic = dt + timedelta(minutes=2)
                        czas_rzeczywisty = czas_oblic.strftime('%H:%M')
            except Exception:
                pass
            
            magazyn_palety.append((
                dto.produkt, dto.waga, sdt, dto.id, dto.plan_id, 
                dto.status, czas_rzeczywisty
            ))
            suma_wykonanie += dto.waga or 0
        
        # Get unconfirmed palety
        unconfirmed_palety = DashboardService._process_unconfirmed_palety(dzisiaj)
        
        return magazyn_palety, unconfirmed_palety, suma_wykonanie

    @staticmethod
    def _process_unconfirmed_palety(dzisiaj: date) -> List[Tuple]:
        """Process unconfirmed palety with elapsed time calculation."""
        try:
            raw = QueryHelper.get_unconfirmed_paletki(dzisiaj)
            out = []
            for r in raw:
                pid = r[0]
                plan_id = r[1]
                produkt = r[2]
                dt = r[3]
                try:
                    sdt = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
                except Exception:
                    sdt = str(dt)
                
                # Get sequence number
                try:
                    seq = QueryHelper.get_paleta_seq_number(plan_id, pid)
                except Exception:
                    seq = None
                
                # Calculate elapsed time
                elapsed = DashboardService._calculate_elapsed_time(dt)
                out.append((pid, plan_id, produkt, sdt, seq, elapsed))
            return out
        except Exception:
            return []

    @staticmethod
    def _calculate_elapsed_time(dt: Any) -> str:
        """Calculate elapsed time from datetime to now."""
        try:
            from datetime import datetime as _dt
            now = _dt.now()
            if hasattr(dt, 'strftime'):
                delta = now - dt
            else:
                try:
                    parsed = _dt.strptime(str(dt), '%Y-%m-%d %H:%M:%S')
                    delta = now - parsed
                except Exception:
                    return ''
            
            if delta:
                secs = int(delta.total_seconds())
                h = secs // 3600
                m = (secs % 3600) // 60
                s = secs % 60
                if h > 0:
                    return f"{h}h {m:02d}m"
                elif m > 0:
                    return f"{m}m {s:02d}s"
                else:
                    return f"{s}s"
        except Exception:
            pass
        return ''

    @staticmethod
    def get_production_plans(dzisiaj: date, sekcja: str) -> Tuple[List, Dict, int, int]:
        """Get production plans for section with formatting and palety mapping.
        
        Returns:
            Tuple of (formatted_plans, palety_mapa, suma_plan, suma_wykonanie)
        """
        plan_dnia = QueryHelper.get_plan_produkcji(
            dzisiaj, 
            sekcja if sekcja != 'Dashboard' else 'Workowanie'
        )
        
        # Fallback for Workowanie
        if sekcja == 'Workowanie' and not plan_dnia:
            plan_dnia = DashboardService._get_workowanie_fallback(dzisiaj)
        
        # Store raw start times before formatting
        plan_start_times = {}
        for p in plan_dnia:
            plan_start_times[p[0]] = p[4] if p[4] else p[3]
        
        # Format times to HH:MM
        for p in plan_dnia:
            try:
                p[4] = p[4].strftime('%H:%M') if p[4] else ''
            except Exception:
                p[4] = str(p[4]) if p[4] else ''
            try:
                p[5] = p[5].strftime('%H:%M') if p[5] else ''
            except Exception:
                p[5] = str(p[5]) if p[5] else ''
        
        # Calculate sums and palety mapping
        palety_mapa = {}
        suma_plan = 0
        suma_wykonanie = 0
        
        for p in plan_dnia:
            if p[7] is None:
                p[7] = 0
            
            # Check if quality order
            is_quality = DashboardService._is_quality_order(p)
            
            if not is_quality:
                suma_plan += p[2] if p[2] else 0
            
            # Get palety for this plan
            if sekcja == 'Magazyn':
                palety = DashboardService._get_palety_for_product(dzisiaj, p[1], p[9])
                palety_mapa[p[0]] = palety
                waga_kg = sum(pal[0] for pal in palety)
                p[7] = waga_kg
                suma_wykonanie += waga_kg
            
            # Calculate Zasyp differences
            if sekcja == 'Zasyp':
                waga_workowania = p[7]
                diff = p[2] - waga_workowania if p[2] else 0
                alert = abs(diff) > 10 if diff else False
                if not is_quality:
                    suma_wykonanie += waga_workowania or 0
                p.extend([waga_workowania, diff, alert])
            
            # Add szarża/paleta count at fixed index p[15]
            count = 0
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                if sekcja == 'Zasyp':
                    cursor.execute(
                        "SELECT COUNT(*) FROM szarze WHERE plan_id = %s AND status = 'zarejestowana'",
                        (p[0],)
                    )
                elif sekcja == 'Workowanie':
                    cursor.execute(
                        "SELECT COUNT(*) FROM palety_workowanie WHERE plan_id = %s",
                        (p[0],)
                    )
                else:
                    cursor = None

                if cursor:
                    fetched = cursor.fetchone()
                    count = fetched[0] if fetched and fetched[0] else 0
                    cursor.close()
                    conn.close()
            except Exception:
                count = 0

            # Ensure list has at least 16 elements so index 15 is valid
            while len(p) <= 15:
                p.append(None)
            p[15] = int(count)
            # Populate palety_mapa for Zasyp/Workowanie when DB has detail rows but palety_mapa wasn't filled earlier
            try:
                if sekcja == 'Zasyp' and p[15] and p[15] > 0 and p[0] not in palety_mapa:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT id, waga, godzina, data_dodania, pracownik_id, status FROM szarze WHERE plan_id = %s AND status = 'zarejestowana' ORDER BY data_dodania ASC",
                        (p[0],)
                    )
                    rows = cursor.fetchall()
                    cursor.close()
                    conn.close()
                    # map to (waga, godzina, id, UNUSED, status) to match template expectations
                    palety_mapa[p[0]] = [(r[1], r[2], r[0], None, r[5] if len(r) > 5 else '') for r in rows]
                    # Calculate sum of szarża weights for Realizacja column p[7]
                    suma_szarzy = sum(r[1] for r in rows)
                    p[7] = suma_szarzy
                    if not is_quality:
                        suma_wykonanie += suma_szarzy
                elif sekcja == 'Workowanie' and p[0] not in palety_mapa:
                    # Use existing query helper to fetch paletki for plan
                    palety = QueryHelper.get_paletki_for_plan(p[0])
                    if palety:
                        # Map to (waga, czas, id, UNUSED, status) to match template expectations
                        # get_paletki_for_plan returns: (id, plan_id, waga, tara, waga_brutto, data_dodania, produkt, typ_produkcji, status, czas_potwierdzenia_s)
                        palety_mapa[p[0]] = [(r[2], r[5], r[0], None, r[8]) for r in palety]
                        # Calculate sum of pallet weights for Realizacja column p[7]
                        suma_palet = sum(r[2] for r in palety)
                        p[7] = suma_palet
                        if not is_quality:
                            suma_wykonanie += suma_palet
            except Exception:
                pass
        
        return plan_dnia, palety_mapa, suma_plan, suma_wykonanie

    @staticmethod
    def _get_workowanie_fallback(dzisiaj: date) -> List:
        """Get Workowanie plans as fallback - with szarża filter."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, produkt, tonaz, status, real_start, real_stop, 
                   TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, 
                   kolejnosc, typ_produkcji, wyjasnienie_rozbieznosci 
                   FROM plan_produkcji p
                   WHERE DATE(p.data_planu) = %s AND p.sekcja = 'Workowanie' 
                   AND p.status IN ('w toku', 'zaplanowane')
                   AND EXISTS (
                       SELECT 1 FROM szarze s
                       INNER JOIN plan_produkcji pr ON s.plan_id = pr.id
                       WHERE s.status = 'zarejestowana'
                         AND DATE(s.data_dodania) = DATE(p.data_planu)
                         AND pr.produkt = p.produkt
                   )
                   ORDER BY CASE p.status WHEN 'w toku' THEN 1 ELSE 2 END, 
                   p.kolejnosc ASC, p.id ASC""",
                (dzisiaj,)
            )
            plan_dnia = [list(r) for r in cursor.fetchall()]
            cursor.close()
            conn.close()
            return plan_dnia
        except Exception:
            return []

    @staticmethod
    def _is_quality_order(plan: List) -> bool:
        """Check if production plan is a quality order."""
        produkt_lower = str(plan[1]).strip().lower() if plan[1] else ''
        
        # Check typ_zlecenia
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(typ_zlecenia, ''), sekcja FROM plan_produkcji WHERE id=%s",
                (plan[0],)
            )
            rz = cursor.fetchone()
            cursor.close()
            conn.close()
            if rz and (str(rz[0]).strip().lower() == 'jakosc' or 
                     (len(rz) > 1 and str(rz[1]).strip() == 'Jakosc')):
                return True
        except Exception:
            pass
        
        # Check product name
        if produkt_lower in ['dezynfekcja linii', 'dezynfekcja']:
            return True
        
        return False

    @staticmethod
    def _get_palety_for_product(dzisiaj: date, product: str, typ_produkcji: str) -> List[Tuple]:
        """Get and format palety for a specific product."""
        raw_pal = QueryHelper.get_paletki_for_product(dzisiaj, product, typ_produkcji)
        palety = []
        
        for r in raw_pal:
            dto = PaletaDTO.from_db_row(r)
            dt = dto.data_dodania
            try:
                sdt = dt.strftime('%H:%M') if hasattr(dt, 'strftime') else str(dt)
                sdt_full = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
            except Exception:
                sdt = str(dt)
                sdt_full = str(dt)
            
            # Format confirmation time
            cps = None
            try:
                if dto.czas_potwierdzenia_s is not None:
                    secs = int(dto.czas_potwierdzenia_s)
                    if secs >= 3600:
                        cps = f"{secs//3600}h {(secs%3600)//60:02d}m"
                    elif secs >= 60:
                        cps = f"{secs//60}m {secs%60:02d}s"
                    else:
                        cps = f"{secs}s"
            except Exception:
                pass
            
            palety.append((
                dto.waga, sdt, dto.id, dto.plan_id, dto.typ_produkcji, 
                dto.tara, dto.waga_brutto, dto.status, cps, sdt_full
            ))
        
        return palety

    @staticmethod
    def any_plan_in_progress(dzisiaj: date) -> bool:
        """Return True if any production plan for the given date has status 'w toku'."""
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM plan_produkcji WHERE DATE(data_planu) = %s AND status = 'w toku'", (dzisiaj,))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            return bool(row and row[0])
        except Exception:
            return False

    @staticmethod
    def get_active_products(dzisiaj: date) -> List[str]:
        """Return list of product names that have a plan with status 'w toku' for Workowanie/Magazyn (not Zasyp).
        
        This prevents blocking Workowanie START when Zasyp is running for same product.
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "SELECT produkt FROM plan_produkcji WHERE DATE(data_planu) = %s AND status = 'w toku' AND sekcja IN ('Workowanie', 'Magazyn')", 
                (dzisiaj,)
            )
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return [r[0] for r in rows if r and r[0]]
        except Exception:
            return []

    @staticmethod
    def get_buffer_queue(dzisiaj: date) -> Dict[str, List[int]]:
        """Build a buffer queue mapping product -> ordered list of Zasyp plan ids.

        Order is by status (w toku first), then kolejnosc, then id to reproduce UI ordering.
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            # Include completed Zasyp plans too and order by completion/ start time
            cursor.execute(
                """SELECT id, produkt, COALESCE(p.real_stop, p.real_start, p.kolejnosc, p.id) as ord
                   FROM plan_produkcji p
                   WHERE DATE(p.data_planu) = %s AND p.sekcja = 'Zasyp' AND p.is_deleted = 0
                   AND p.status IN ('w toku', 'zaplanowane', 'zakonczone')
                   ORDER BY ord ASC, p.kolejnosc ASC, p.id ASC""",
                (dzisiaj,)
            )
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            queue: Dict[str, List[int]] = {}
            for r in rows:
                if not r or len(r) < 2:
                    continue
                pid = r[0]
                prod = r[1]
                if prod not in queue:
                    queue[prod] = []
                queue[prod].append(pid)
            return queue
        except Exception:
            return {}

    @staticmethod
    def get_first_workowanie_map(dzisiaj: date) -> Dict[str, int]:
        """Return a map product -> first Workowanie plan id (by status then kolejnosc).

        This determines which Workowanie plan should be started first per product.
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """SELECT id, produkt FROM plan_produkcji p
                   WHERE DATE(p.data_planu) = %s AND p.sekcja = 'Workowanie' AND p.is_deleted = 0
                   AND p.status IN ('w toku', 'zaplanowane')
                   ORDER BY CASE p.status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 ELSE 3 END, p.kolejnosc ASC, p.id ASC""",
                (dzisiaj,)
            )
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            first_map: Dict[str, int] = {}
            for r in rows:
                if not r or len(r) < 2:
                    continue
                pid = r[0]
                prod = r[1]
                if prod not in first_map:
                    first_map[prod] = pid
            return first_map
        except Exception:
            return {}

    @staticmethod
    def get_zasyp_product_order(dzisiaj: date) -> Dict[str, int]:
        """Return a numbering (1-based) for products according to Zasyp execution order.

        Orders all Zasyp plans for the day by completion/start time and assigns the first
        occurrence of each product an incremental position.
        """
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                """SELECT produkt, COALESCE(p.real_stop, p.real_start, p.kolejnosc, p.id) as ord
                   FROM plan_produkcji p
                   WHERE DATE(p.data_planu) = %s AND p.sekcja = 'Zasyp' AND p.is_deleted = 0
                   AND p.status IN ('w toku', 'zaplanowane', 'zakonczone')
                   ORDER BY ord ASC, p.kolejnosc ASC, p.id ASC""",
                (dzisiaj,)
            )
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            order_map: Dict[str, int] = {}
            pos = 1
            for r in rows:
                if not r or len(r) < 1:
                    continue
                prod = r[0]
                if prod not in order_map:
                    order_map[prod] = pos
                    pos += 1
            return order_map
        except Exception:
            return {}

    @staticmethod
    def get_hr_and_leave_data(dzisiaj: date, wszyscy: List, zajeci_ids: set) -> Dict[str, Any]:
        """Get HR records, leave data, and staff availability."""
        # Get presence records
        raporty_hr = QueryHelper.get_presence_records_for_day(dzisiaj)
        
        # Get absence data
        try:
            ob = QueryHelper.get_absence_ids_for_day(dzisiaj)
            ob_all_ids = set(r[0] for r in ob)
            ob_nonprivate_ids = set(r[0] for r in ob if str(r[1]).strip().lower() != 'wyjscie prywatne')
            hr_dostepni = [p for p in wszyscy if p[0] not in ob_nonprivate_ids]
            hr_pracownicy = [p for p in wszyscy if p[0] not in ob_all_ids and p[0] not in zajeci_ids]
        except Exception:
            hr_dostepni = [p for p in wszyscy if p[0] not in zajeci_ids]
            hr_pracownicy = [p for p in wszyscy if p[0] not in zajeci_ids]
        
        # Get leave data
        planned_leaves = QueryHelper.get_planned_leaves(days_ahead=60, limit=500)
        recent_absences = QueryHelper.get_recent_absences(days_back=30, limit=500)
        
        return {
            'raporty_hr': raporty_hr,
            'hr_dostepni': hr_dostepni,
            'hr_pracownicy': hr_pracownicy,
            'planned_leaves': planned_leaves,
            'recent_absences': recent_absences,
        }

    @staticmethod
    def get_quality_and_leave_requests(role: str) -> Dict[str, Any]:
        """Get quality orders count and pending leave requests for leaders."""
        quality_count = QueryHelper.get_pending_quality_count()
        wnioski_pending = []
        
        try:
            if role.lower() in ['lider', 'admin']:
                wnioski_pending = QueryHelper.get_pending_leave_requests(limit=50)
        except Exception:
            pass
        
        return {
            'quality_count': quality_count,
            'wnioski_pending': wnioski_pending,
        }

    @staticmethod
    def get_shift_notes() -> List[Dict[str, Any]]:
        """Get shift notes from database."""
        shift_notes = []
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Create table if not exists
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS shift_notes (
                        id BIGINT PRIMARY KEY,
                        pracownik_id INT,
                        note TEXT,
                        author VARCHAR(255),
                        date DATE,
                        created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """)
            except Exception:
                pass
            
            cursor.execute(
                "SELECT id, pracownik_id, DATE_FORMAT(date, '%Y-%m-%d'), note, author, created "
                "FROM shift_notes ORDER BY created DESC LIMIT 200"
            )
            rows = cursor.fetchall()
            for r in rows:
                shift_notes.append({
                    'id': r[0],
                    'pracownik_id': r[1],
                    'date': r[2],
                    'note': r[3],
                    'author': r[4],
                    'created': r[5]
                })
            cursor.close()
            conn.close()
        except Exception:
            pass
        
        return shift_notes

    @staticmethod
    def get_full_plans_for_sections(dzisiaj: date) -> Tuple[List, List]:
        """Get full production plans for Zasyp and Workowanie sections."""
        plans_zasyp = []
        plans_workowanie = []
        
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Zasyp: fetch all plans
            cursor.execute(
                """SELECT id, produkt, tonaz, status, real_start, real_stop, 
                   TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, 
                   kolejnosc, typ_produkcji, wyjasnienie_rozbieznosci, uszkodzone_worki 
                   FROM plan_produkcji 
                   WHERE DATE(data_planu) = %s AND sekcja = 'Zasyp' AND status != 'nieoplacone' 
                   AND is_deleted = 0 
                   ORDER BY CASE status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 
                   ELSE 3 END, kolejnosc ASC, id ASC""",
                (dzisiaj,)
            )
            plans_zasyp = [list(r) for r in cursor.fetchall()]
            
            # Workowanie: fetch ONLY plans that have szarża (buffer) with status='zarejestowana'
            cursor.execute(
                """SELECT id, produkt, tonaz, status, real_start, real_stop, 
                   TIMESTAMPDIFF(MINUTE, real_start, real_stop), tonaz_rzeczywisty, 
                   kolejnosc, typ_produkcji, wyjasnienie_rozbieznosci, uszkodzone_worki 
                   FROM plan_produkcji p
                   WHERE DATE(p.data_planu) = %s AND p.sekcja = 'Workowanie' AND p.status != 'nieoplacone' 
                   AND p.is_deleted = 0
                   AND EXISTS (
                       SELECT 1 FROM szarze s
                       INNER JOIN plan_produkcji pr ON s.plan_id = pr.id
                       WHERE s.status = 'zarejestowana'
                         AND DATE(s.data_dodania) = DATE(p.data_planu)
                         AND pr.produkt = p.produkt
                   )
                   ORDER BY CASE p.status WHEN 'w toku' THEN 1 WHEN 'zaplanowane' THEN 2 
                   ELSE 3 END, p.kolejnosc ASC, p.id ASC""",
                (dzisiaj,)
            )
            plans_workowanie = [list(r) for r in cursor.fetchall()]
            
            # Format times for all plans
            for rows in [plans_zasyp, plans_workowanie]:
                for p in rows:
                    try:
                        p[4] = p[4].strftime('%H:%M') if p[4] else ''
                    except Exception:
                        p[4] = str(p[4]) if p[4] else ''
                    try:
                        p[5] = p[5].strftime('%H:%M') if p[5] else ''
                    except Exception:
                        p[5] = str(p[5]) if p[5] else ''
                    if p[7] is None:
                        p[7] = 0
            
            cursor.close()
            conn.close()
        except Exception:
            pass
        
        return plans_zasyp, plans_workowanie

    @staticmethod
    def get_zasyp_started_products(dzisiaj: date) -> List:
        """Get started Zasyp products."""
        try:
            return QueryHelper.get_zasyp_started_produkty(dzisiaj)
        except Exception:
            return []

    @staticmethod
    def get_next_workowanie_id(plan_dnia: List) -> Optional[int]:
        """Get next planned Workowanie order ID."""
        kandydaci = [p for p in plan_dnia if p[3] == 'zaplanowane']
        kandydaci.sort(key=lambda x: x[0])
        return kandydaci[0][0] if kandydaci else None
