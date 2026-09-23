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
            # 1. Surowce w OSIP / A01..A99 / BFOS / OSxx
            query_sur = """
                SELECT id, nr_palety, nazwa, stan_magazynowy, stan_magazynowy as ilosc_kg, data_przydatnosci, nr_partii, lokalizacja, 'raw' as item_type
                FROM magazyn_surowce
                WHERE stan_magazynowy > 0 AND (lokalizacja = 'OSIP' OR lokalizacja LIKE 'OS%' OR lokalizacja LIKE 'A%' OR lokalizacja = 'BFOS')
            """
            cursor.execute(query_sur)
            raw_materials = cursor.fetchall()

            # 2. Wyroby Gotowe w OSIP / A01..A99 / BFOS / OSxx
            query_fg = """
                SELECT id, nr_palety, 'Wyrób Gotowy' as nazwa, waga as ilosc_kg, waga as stan_magazynowy, data_dodania as data_przydatnosci, 'brak' as nr_partii, lokalizacja, 'fg' as item_type
                FROM palety_workowanie
                WHERE (lokalizacja = 'OSIP' OR lokalizacja LIKE 'OS%' OR lokalizacja LIKE 'A%' OR lokalizacja = 'BFOS')
            """
            try:
                cursor.execute(query_fg)
                finished_goods = cursor.fetchall()
            except Exception:
                finished_goods = []

            # Filtrowanie wyszukiwaniem (dla cyfr szukamy od konca - suffix matching)
            if search_term:
                term = str(search_term).strip().lower()
                is_pure_digits = term.isdigit()

                def _matches_item(item: Dict[str, Any]) -> bool:
                    nr_p = str(item.get('nr_palety', '')).strip().lower()
                    nazwa = str(item.get('nazwa', '')).strip().lower()
                    lok = str(item.get('lokalizacja', '')).strip().lower()
                    batch = str(item.get('nr_partii', '')).strip().lower()

                    if is_pure_digits:
                        nr_digits = ''.join(c for c in nr_p if c.isdigit())
                        batch_digits = ''.join(c for c in batch if c.isdigit())
                        return (
                            (nr_digits and nr_digits.endswith(term))
                            or nr_p.endswith(term)
                            or (batch_digits and batch_digits.endswith(term))
                            or term in nazwa
                            or term in lok
                        )
                    return (term in nr_p or term in nazwa or term in lok or term in batch)

                raw_materials = [r for r in raw_materials if _matches_item(r)]
                finished_goods = [f for f in finished_goods if _matches_item(f)]

            return {
                "raw_materials": raw_materials,
                "finished_goods": finished_goods,
                "total_raw": len(raw_materials),
                "total_fg": len(finished_goods)
            }
        finally:
            cursor.close()
            conn.close()

    def get_osip_grouped_inventory(self, search_term: str = "") -> List[Dict[str, Any]]:
        """Pobiera surowce z lokalizacji OSIP zgrupowane według nazwy surowca."""
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            query = """
                SELECT id, nr_palety, nazwa, stan_magazynowy, nr_partii, lokalizacja, typ_opakowania, data_przydatnosci, created_at
                FROM magazyn_surowce
                WHERE stan_magazynowy > 0 AND (lokalizacja = 'OSIP' OR lokalizacja LIKE 'OS%' OR lokalizacja LIKE 'A%' OR lokalizacja = 'BFOS')
                ORDER BY nazwa ASC, id ASC
            """
            cursor.execute(query)
            items = cursor.fetchall()
            
            # Grupowanie według nazwy
            grouped: Dict[str, Dict[str, Any]] = {}
            for it in items:
                name = it.get('nazwa') or 'Nieznany surowiec'
                if search_term:
                    term = search_term.lower()
                    if term not in name.lower() and term not in str(it.get('nr_palety', '')).lower() and term not in str(it.get('nr_partii', '')).lower() and term not in str(it.get('lokalizacja', '')).lower():
                        continue
                if name not in grouped:
                    grouped[name] = {
                        'nazwa': name,
                        'total_kg': 0.0,
                        'pallet_count': 0,
                        'pallets': [],
                        'batches': set(),
                        'locations': set()
                    }
                qty = float(it.get('stan_magazynowy') or 0)
                grouped[name]['total_kg'] += qty
                grouped[name]['pallet_count'] += 1
                grouped[name]['pallets'].append(it)
                if it.get('nr_partii'):
                    grouped[name]['batches'].add(str(it['nr_partii']))
                if it.get('lokalizacja'):
                    grouped[name]['locations'].add(str(it['lokalizacja']))
            
            result = []
            for name, g in sorted(grouped.items(), key=lambda x: x[0]):
                result.append({
                    'nazwa': g['nazwa'],
                    'total_kg': round(g['total_kg'], 2),
                    'pallet_count': g['pallet_count'],
                    'pallets': g['pallets'],
                    'batches': sorted(list(g['batches'])),
                    'locations': sorted(list(g['locations']))
                })
            return result
        finally:
            cursor.close()
            conn.close()

    def get_osip_layout_stats(self) -> Dict[str, Any]:
        """Pobiera strukturę alejek OSIP (A01-A99 oraz BFOS, oraz kompatybilne OS01-OS77) wraz ze statystykami obłożenia."""
        inventory = self.get_osip_inventory()
        all_items = inventory["raw_materials"] + inventory["finished_goods"]

        aisles = {}
        # Generowanie alejek A01..A99
        for i in range(1, 100):
            aisle_code = f"A{str(i).zfill(2)}"
            aisles[aisle_code] = {
                "id": aisle_code,
                "number": i,
                "items": [],
                "count": 0
            }

        # Generowanie strefy BFOS
        aisles["BFOS"] = {
            "id": "BFOS",
            "number": 100,
            "items": [],
            "count": 0
        }

        unallocated_osip = []
        for item in all_items:
            loc = str(item.get("lokalizacja", "")).strip().upper()
            if loc in aisles:
                aisles[loc]["items"].append(item)
                aisles[loc]["count"] += 1
            else:
                unallocated_osip.append(item)

        return {
            "total_aisles": len(aisles),
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
