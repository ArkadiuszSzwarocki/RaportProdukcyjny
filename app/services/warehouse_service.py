"""
Wersja: 1.1.0
Opis: Serwis magazynowy. Zarządza danymi palet i stanami magazynowymi.
"""
from datetime import date
from typing import Dict, List, Tuple, Any, Optional
from app.db import get_db_connection, get_table_name
from app.utils.queries import QueryHelper
from app.dto.paleta import PaletaDTO

class WarehouseService:
    @staticmethod
    def get_warehouse_data(dzisiaj: date, linia='PSD', cursor=None) -> Tuple[List[Tuple], List[Tuple], int]:
        """Get warehouse (Magazyn) palety and unconfirmed palety."""
        raw_mag = QueryHelper.get_paletki_magazyn(dzisiaj, linia=linia, cursor=cursor)
        magazyn_palety = []
        suma_wykonanie = 0
        
        for r in raw_mag:
            dto = PaletaDTO.from_db_row(r)
            dt = dto.data_dodania
            try:
                sdt = dt.strftime('%H:%M') if hasattr(dt, 'strftime') else str(dt)
            except Exception:
                sdt = str(dt)
            
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
                        czas_rzeczywisty = dt.strftime('%H:%M')
                    else:
                        czas_rzeczywisty = str(dt) if dt else '-'
            except Exception:
                pass
            
            magazyn_palety.append((
                dto.produkt, dto.waga, czas_rzeczywisty, dto.id, dto.plan_id,
                dto.status, sdt, dto.user_login, dto.nr_palety, dto.nr_plomby
            ))
            suma_wykonanie += dto.waga or 0
        
        unconfirmed_palety = WarehouseService.process_unconfirmed_palety(dzisiaj, linia=linia, cursor=cursor)
        
        return magazyn_palety, unconfirmed_palety, suma_wykonanie

    @staticmethod
    def process_unconfirmed_palety(dzisiaj: date, linia='PSD', cursor=None) -> List[Tuple]:
        """Process unconfirmed palety with elapsed time calculation."""
        try:
            raw = QueryHelper.get_unconfirmed_paletki(dzisiaj, linia=linia, cursor=cursor)
            out = []
            for r in raw:
                pid = r[0]
                plan_id = r[1]
                produkt = r[2]
                dt = r[3]
                sdt = dt.strftime('%Y-%m-%d %H:%M:%S') if hasattr(dt, 'strftime') else str(dt)
                seq = r[4] if len(r) > 4 else None
                nr_palety = r[5] if len(r) > 5 else None
                
                elapsed = WarehouseService.calculate_elapsed_time(dt)
                out.append((pid, plan_id, produkt, sdt, seq, elapsed, nr_palety))
            return out
        except Exception:
            return []

    @staticmethod
    def calculate_elapsed_time(dt: Any) -> str:
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
    def get_palety_for_plans_batch(dzisiaj: date, plans: List, linia='PSD', cursor=None) -> Dict[int, List]:
        """Fetch all pallets for multiple products/plans in one go (Batching)."""
        if not plans:
            return {}
            
        products = list(set(p[1] for p in plans))
        table_palety = get_table_name('palety_workowanie', linia)
        table_plan = get_table_name('plan_produkcji', linia)
        
        fmt_products = ",".join(["%s"] * len(products))
        cursor.execute(
            f"SELECT pw.id, pw.plan_id, pw.waga, pw.tara, pw.waga_brutto, pw.data_dodania, "
            f"p.produkt, p.typ_produkcji, COALESCE(pw.status, ''), pw.czas_potwierdzenia_s "
            f"FROM {table_palety} pw JOIN {table_plan} p ON pw.plan_id = p.id "
            f"WHERE DATE(p.data_planu) = %s AND p.produkt IN ({fmt_products}) AND p.sekcja IN ('Workowanie', 'Czyszczenie') "
            "ORDER BY pw.id DESC",
            (dzisiaj, *products)
        )
        
        all_palety = cursor.fetchall()
        # Group by plan_id
        palety_mapa = {}
        for r in all_palety:
            plan_id = r[1]
            palety_mapa.setdefault(plan_id, []).append(r)
            
        return palety_mapa
