"""
Serwis obsługujący stan magazynowy OSIP oraz podgląd układu hali alejek OS01-OS77.
"""
from typing import Dict, List, Any
from app.core.database import get_db_connection


class OsipWarehouseService:
    OSIP_LOCATION_PREFIX = "OS"
    TOTAL_AISLES = 77

    def get_osip_inventory(self, search_term: str = "") -> Dict[str, List[Dict[str, Any]]]:
        """Pobiera surowce oraz wyroby gotowe znajdujące się w lokalizacjach OSIP lub OS01..OS77."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            # 1. Surowce w OSIP / OSxx
            query_sur = """
                SELECT id, nr_palety, nazwa, stan_magazynowy, stan_magazynowy as ilosc_kg, data_przydatnosci, nr_partii, lokalizacja, 'raw' as item_type
                FROM magazyn_surowce
                WHERE stan_magazynowy > 0 AND (lokalizacja = 'OSIP' OR lokalizacja LIKE 'OS%')
            """
            cursor.execute(query_sur)
            raw_materials = cursor.fetchall()

            # 2. Wyroby Gotowe w OSIP / OSxx (sprawdzamy tabele palety_workowanie lub magazyn_wyroby_gotowe)
            query_fg = """
                SELECT id, nr_palety, 'Wyrób Gotowy' as nazwa, waga as ilosc_kg, waga as stan_magazynowy, data_dodania as data_przydatnosci, 'brak' as nr_partii, lokalizacja, 'fg' as item_type
                FROM palety_workowanie
                WHERE (lokalizacja = 'OSIP' OR lokalizacja LIKE 'OS%')
            """
            try:
                cursor.execute(query_fg)
                finished_goods = cursor.fetchall()
            except Exception:
                finished_goods = []

            # Filtrowanie wyszukiwaniem
            if search_term:
                term = search_term.lower()
                raw_materials = [
                    r for r in raw_materials
                    if term in str(r.get('nr_palety', '')).lower() or term in str(r.get('nazwa', '')).lower() or term in str(r.get('lokalizacja', '')).lower()
                ]
                finished_goods = [
                    f for f in finished_goods
                    if term in str(f.get('nr_palety', '')).lower() or term in str(f.get('nazwa', '')).lower() or term in str(f.get('lokalizacja', '')).lower()
                ]

            return {
                "raw_materials": raw_materials,
                "finished_goods": finished_goods,
                "total_raw": len(raw_materials),
                "total_fg": len(finished_goods)
            }
        finally:
            cursor.close()
            conn.close()

    def get_osip_layout_stats(self) -> Dict[str, Any]:
        """Pobiera strukturę 77 alejek (OS01-OS77) wraz ze statystykami obłożenia."""
        inventory = self.get_osip_inventory()
        all_items = inventory["raw_materials"] + inventory["finished_goods"]

        aisles = {}
        for i in range(1, self.TOTAL_AISLES + 1):
            aisle_code = f"OS{str(i).zfill(2)}"
            aisles[aisle_code] = {
                "id": aisle_code,
                "number": i,
                "items": [],
                "count": 0
            }

        unallocated_osip = []
        for item in all_items:
            loc = str(item.get("lokalizacja", "")).strip()
            if loc in aisles:
                aisles[loc]["items"].append(item)
                aisles[loc]["count"] += 1
            else:
                unallocated_osip.append(item)

        return {
            "total_aisles": self.TOTAL_AISLES,
            "aisles": list(aisles.values()),
            "unallocated_osip": unallocated_osip,
            "total_occupancy": len(all_items)
        }

    def get_osip_expeditions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Pobiera historię wydań zewnętrznych (EXPEDITION) z Magazynu OSIP."""
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT id, nr_palety, nazwa, typ_palety, linia, nr_partii, waga_ostatnia as ilosc, 
                       lokalizacja_ostatnia, user_login, komentarz, data_archiwizacji as created_at
                FROM magazyn_archiwum
                WHERE (lokalizacja_ostatnia = 'EXPEDITION' AND (komentarz LIKE '%z OSIP%' OR komentarz LIKE '%z OS%' OR komentarz LIKE '%Wydanie Zewnętrzne OSIP%'))
                   OR (lokalizacja_ostatnia LIKE 'OS%' AND typ_palety IS NOT NULL)
                ORDER BY id DESC LIMIT %s
            """, (limit,))
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("SELECT id, nr_palety, nazwa, typ_palety, linia, nr_partii, waga_ostatnia as ilosc, lokalizacja_ostatnia, user_login, komentarz, data_archiwizacji as created_at FROM magazyn_archiwum WHERE lokalizacja_ostatnia = 'EXPEDITION' ORDER BY id DESC LIMIT %s", (limit,))
                rows = cursor.fetchall()
            return rows
        finally:
            conn.close()

    def dispatch_osip_pallet(self, pallet_id: int, pallet_type: str, worker_login: str, customer_name: str = "", notes: str = "", linia: str = "PSD"):
        """Wydanie zewnętrzne palety bezpośrednio z Magazynu OSIP (EXPEDITION)."""
        from app.services.warehouse_v2_service import WarehouseV2Service
        return WarehouseV2Service.dispatch_pallet(pallet_id, pallet_type, worker_login, linia)
