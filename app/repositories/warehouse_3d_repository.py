"""
Warehouse 3D Data Access Repository.
Queries all active warehouse stock items across raw materials, packaging, additives, and finished products.
"""
from typing import List, Dict, Any, Optional
from app.db import get_db_connection, get_table_name

class Warehouse3dRepository:
    """Repository handling SQL queries for 3D warehouse visualization."""

    @staticmethod
    def fetch_all_active_stock(linia: str = 'ALL') -> List[Dict[str, Any]]:
        """
        Fetches all active stock records from all relevant warehouse tables.
        Normalizes column names across surowce, opakowania, dodatki, and palety (PSD & AGRO).
        """
        conn = get_db_connection()
        items: List[Dict[str, Any]] = []
        try:
            cursor = conn.cursor(dictionary=True)
            norm_linia = str(linia or 'ALL').upper()

            # 1. Raw Materials (Surowce)
            try:
                cursor.execute("""
                    SELECT id, nr_palety, nazwa as productName, lokalizacja as location, 
                           stan_magazynowy as amount, 'Surowiec' as pallet_type, 
                           data_produkcji, data_przydatnosci, nr_partii, is_blocked, 
                           typ_opakowania, created_at, COALESCE(linia, 'PSD') as linia
                    FROM magazyn_surowce 
                    WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''
                """)
                rows = cursor.fetchall() or []
                if norm_linia != 'ALL':
                    rows = [r for r in rows if str(r.get('linia') or 'PSD').upper() == norm_linia]
                items.extend(rows)
            except Exception as e:
                print(f"[Warehouse3dRepository] Error fetching surowce: {e}")

            # 2. Packaging (Opakowania)
            try:
                cursor.execute("""
                    SELECT id, nr_palety, nazwa as productName, lokalizacja as location, 
                           stan_magazynowy as amount, 'Opakowanie' as pallet_type, 
                           data_produkcji, data_przydatnosci, nr_partii, is_blocked, 
                           'opakowanie' as typ_opakowania, created_at, COALESCE(linia, 'PSD') as linia
                    FROM magazyn_opakowania 
                    WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''
                """)
                rows = cursor.fetchall() or []
                if norm_linia != 'ALL':
                    rows = [r for r in rows if str(r.get('linia') or 'PSD').upper() == norm_linia]
                items.extend(rows)
            except Exception as e:
                print(f"[Warehouse3dRepository] Error fetching opakowania: {e}")

            # 3. Additives (Dodatki)
            try:
                cursor.execute("""
                    SELECT id, nr_palety, nazwa as productName, lokalizacja as location, 
                           stan_magazynowy as amount, 'Dodatek' as pallet_type, 
                           data_produkcji, data_przydatnosci, nr_partii, is_blocked, 
                           'worek' as typ_opakowania, created_at, COALESCE(linia, 'PSD') as linia
                    FROM magazyn_dodatki 
                    WHERE stan_magazynowy > 0 AND lokalizacja IS NOT NULL AND lokalizacja <> ''
                """)
                rows = cursor.fetchall() or []
                if norm_linia != 'ALL':
                    rows = [r for r in rows if str(r.get('linia') or 'PSD').upper() == norm_linia]
                items.extend(rows)
            except Exception as e:
                print(f"[Warehouse3dRepository] Error fetching dodatki: {e}")

            # 4. Finished Goods PSD (magazyn_palety)
            if norm_linia in ('ALL', 'PSD'):
                try:
                    cursor.execute("""
                        SELECT m.id, m.nr_palety, 
                               COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Wyrób gotowy PSD') as productName, 
                               m.lokalizacja as location, 
                               m.waga_netto as amount, 
                               'Wyrób Gotowy' as pallet_type, 
                               COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji, m.data_planu, plan.data_planu) as data_produkcji, 
                               COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci, 
                               COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii) as nr_partii, 
                               m.is_blocked, 
                               COALESCE(m.typ_opakowania, plan.typ_opakowania, 'worek') as typ_opakowania,
                               COALESCE(m.created_at, m.data_potwierdzenia) as created_at,
                               'PSD' as linia
                        FROM magazyn_palety m
                        LEFT JOIN plan_produkcji plan ON m.plan_id = plan.id
                        WHERE m.waga_netto > 0 AND m.lokalizacja IS NOT NULL AND m.lokalizacja <> ''
                    """)
                    items.extend(cursor.fetchall() or [])
                except Exception as e:
                    print(f"[Warehouse3dRepository] Error fetching wyroby gotowe PSD: {e}")

            # 5. Finished Goods AGRO (magazyn_palety_agro)
            if norm_linia in ('ALL', 'AGRO'):
                try:
                    cursor.execute("""
                        SELECT m.id, m.nr_palety, 
                               COALESCE(NULLIF(TRIM(m.produkt), ''), plan.produkt, 'Wyrób gotowy AGRO') as productName, 
                               m.lokalizacja as location, 
                               m.waga_netto as amount, 
                               'Wyrób Gotowy' as pallet_type, 
                               COALESCE(NULLIF(TRIM(m.data_produkcji), ''), plan.data_produkcji, m.data_planu, plan.data_planu) as data_produkcji, 
                               COALESCE(NULLIF(TRIM(m.data_przydatnosci), ''), plan.termin_przydatnosci) as data_przydatnosci, 
                               COALESCE(NULLIF(TRIM(m.nr_partii), ''), plan.nr_partii) as nr_partii, 
                               m.is_blocked, 
                               COALESCE(m.typ_opakowania, plan.typ_opakowania, 'worek') as typ_opakowania,
                               COALESCE(m.created_at, m.data_potwierdzenia) as created_at,
                               'AGRO' as linia
                        FROM magazyn_palety_agro m
                        LEFT JOIN plan_produkcji_agro plan ON m.plan_id = plan.id
                        WHERE m.waga_netto > 0 AND m.lokalizacja IS NOT NULL AND m.lokalizacja <> ''
                    """)
                    items.extend(cursor.fetchall() or [])
                except Exception as e:
                    print(f"[Warehouse3dRepository] Error fetching wyroby gotowe AGRO: {e}")

            cursor.close()
        finally:
            conn.close()

        return items

