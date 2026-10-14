"""Repository querying available warehouse pallets associated with production station materials."""
from __future__ import annotations

import re
from typing import List, Dict, Any, Optional
from app.db import get_db_connection, get_table_name


_LOCATION_SQL = "UPPER(REPLACE(REPLACE(REPLACE(TRIM(COALESCE(lokalizacja, '')), '_', ''), '-', ''), ' ', ''))"
_WAREHOUSE_SCOPE_SQL = f"({_LOCATION_SQL} IN ('MP01', 'BFMP01', 'MDO01') OR {_LOCATION_SQL} REGEXP '^R[0-9]+$')"


class StationWarehouseMaterialRepository:
    """Read-only repository for querying warehouse pallet inventory for station materials."""

    @staticmethod
    def find_station_assigned_materials(station_code: str) -> List[str]:
        """Fetch material names configured for the station in rules table."""
        if not station_code:
            return []

        norm_code = str(station_code).strip().upper()
        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                """
                SELECT nazwa_surowca
                FROM konfiguracja_zbiornikow
                WHERE UPPER(TRIM(kod_zbiornika)) = %s AND is_active = 1
                """,
                (norm_code,)
            )
            rows = cursor.fetchall()
            names = []
            for r in rows:
                val = (r.get("nazwa_surowca") or "").strip()
                if val and val not in names:
                    names.append(val)
            return names
        except Exception:
            return []
        finally:
            conn.close()

    @staticmethod
    def find_available_pallets_for_assigned_material(
        material_name: str,
        linia: str = "AGRO",
        exclude_location: str = ""
    ) -> List[Dict[str, Any]]:
        """Query available pallets in warehouse (MP01, Regały, Bufory) matching ONLY the assigned material."""
        clean_name = str(material_name or "").strip()
        if not clean_name:
            return []

        table_surowce = get_table_name("magazyn_surowce", linia)
        norm_exclude = str(exclude_location or "").strip().upper()

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            exclude_cond = ""
            params_exact: List[Any] = [norm_exclude, clean_name.upper()] if norm_exclude else [clean_name.upper()]
            if norm_exclude:
                exclude_cond = "AND UPPER(COALESCE(lokalizacja, '')) != %s"

            # 1. First attempt: EXACT case-insensitive match for the assigned material
            sql_exact = f"""
                SELECT
                    id,
                    COALESCE(nr_palety, CONCAT('SUR-', id)) AS nr_palety,
                    nazwa,
                    stan_magazynowy,
                    COALESCE(lokalizacja, '') AS lokalizacja,
                    COALESCE(nr_partii, '') AS nr_partii,
                    data_produkcji,
                    data_przydatnosci,
                    'kg' AS jednostka
                FROM {table_surowce}
                WHERE stan_magazynowy > 0
                  AND COALESCE(is_blocked, 0) = 0
                  AND {_WAREHOUSE_SCOPE_SQL}
                  {exclude_cond}
                  AND UPPER(TRIM(nazwa)) = %s
                ORDER BY
                    CASE
                        WHEN UPPER(lokalizacja) = 'MP01' THEN 1
                        WHEN UPPER(lokalizacja) LIKE 'BF%%' THEN 2
                        WHEN UPPER(lokalizacja) REGEXP '^R[0-9]' THEN 3
                        ELSE 4
                    END ASC,
                    lokalizacja ASC,
                    id ASC
                LIMIT 150
            """

            cursor.execute(sql_exact, tuple(params_exact))
            rows = cursor.fetchall() or []

            # 2. Second attempt: if 0 rows, try flexible contains match for the material
            if not rows and len(clean_name) >= 3:
                params_like: List[Any] = [norm_exclude, f"%{clean_name.upper()}%"] if norm_exclude else [f"%{clean_name.upper()}%"]

                sql_like = f"""
                    SELECT
                        id,
                        COALESCE(nr_palety, CONCAT('SUR-', id)) AS nr_palety,
                        nazwa,
                        stan_magazynowy,
                        COALESCE(lokalizacja, '') AS lokalizacja,
                        COALESCE(nr_partii, '') AS nr_partii,
                        data_produkcji,
                        data_przydatnosci,
                        'kg' AS jednostka
                    FROM {table_surowce}
                    WHERE stan_magazynowy > 0
                      AND COALESCE(is_blocked, 0) = 0
                      AND {_WAREHOUSE_SCOPE_SQL}
                      {exclude_cond}
                      AND UPPER(nazwa) LIKE %s
                    ORDER BY
                        CASE
                            WHEN UPPER(lokalizacja) = 'MP01' THEN 1
                            WHEN UPPER(lokalizacja) LIKE 'BF%%' THEN 2
                            WHEN UPPER(lokalizacja) REGEXP '^R[0-9]' THEN 3
                            ELSE 4
                        END ASC,
                        lokalizacja ASC,
                        id ASC
                    LIMIT 150
                """
                cursor.execute(sql_like, tuple(params_like))
                rows = cursor.fetchall() or []

            results = []
            for r in rows:
                dp = r.get("data_produkcji")
                dp_str = dp.strftime("%Y-%m-%d") if hasattr(dp, "strftime") else (str(dp) if dp else "")
                dz = r.get("data_przydatnosci")
                dz_str = dz.strftime("%Y-%m-%d") if hasattr(dz, "strftime") else (str(dz) if dz else "")

                results.append({
                    "id": r["id"],
                    "nr_palety": r["nr_palety"],
                    "nazwa": r["nazwa"] or "",
                    "stan_magazynowy": float(r["stan_magazynowy"] or 0),
                    "lokalizacja": r["lokalizacja"] or "",
                    "nr_partii": r["nr_partii"] or "",
                    "data_produkcji": dp_str,
                    "data_przydatnosci": dz_str,
                    "jednostka": r.get("jednostka") or "kg",
                    "typ": "Surowiec"
                })

            return results
        except Exception:
            return []
        finally:
            conn.close()

    @staticmethod
    def find_available_pallets_by_material_names(
        material_names: List[str],
        linia: str = "AGRO",
        exclude_location: str = ""
    ) -> List[Dict[str, Any]]:
        """Query available pallets in warehouse (MP01, Regały, Bufory) matching specified materials."""
        if not material_names:
            return []

        clean_names = [n.strip() for n in material_names if n and n.strip()]
        if not clean_names:
            return []

        table_surowce = get_table_name("magazyn_surowce", linia)
        norm_exclude = str(exclude_location or "").strip().upper()

        conn = get_db_connection()
        try:
            cursor = conn.cursor(dictionary=True)

            # Build WHERE conditions for material matching (exact or LIKE keywords)
            name_conditions = []
            params: List[Any] = []

            for name in clean_names:
                # Direct case-insensitive match or contains
                name_conditions.append("UPPER(TRIM(nazwa)) = %s")
                params.append(name.upper())

                # Also match if database name contains keyword (min 3 chars)
                if len(name) >= 3:
                    name_conditions.append("UPPER(nazwa) LIKE %s")
                    params.append(f"%{name.upper()}%")

            where_names_clause = " OR ".join(name_conditions)

            # Exclude production stations and transient locations
            exclude_cond = ""
            if norm_exclude:
                exclude_cond = "AND UPPER(COALESCE(lokalizacja, '')) != %s"
                params.insert(0, norm_exclude)

            sql = f"""
                SELECT
                    id,
                    COALESCE(nr_palety, CONCAT('SUR-', id)) AS nr_palety,
                    nazwa,
                    stan_magazynowy,
                    COALESCE(lokalizacja, '') AS lokalizacja,
                    COALESCE(nr_partii, '') AS nr_partii,
                    data_produkcji,
                    data_przydatnosci,
                    'kg' AS jednostka
                FROM {table_surowce}
                WHERE stan_magazynowy > 0
                  AND COALESCE(is_blocked, 0) = 0
                  AND {_WAREHOUSE_SCOPE_SQL}
                  {exclude_cond}
                  AND ({where_names_clause})
                ORDER BY
                    CASE
                        WHEN UPPER(lokalizacja) = 'MP01' THEN 1
                        WHEN UPPER(lokalizacja) LIKE 'BF%%' THEN 2
                        WHEN UPPER(lokalizacja) REGEXP '^R[0-9]' THEN 3
                        ELSE 4
                    END ASC,
                    lokalizacja ASC,
                    id ASC
                LIMIT 150
            """

            cursor.execute(sql, tuple(params))
            rows = cursor.fetchall() or []

            results = []
            for r in rows:
                dp = r.get("data_produkcji")
                dp_str = dp.strftime("%Y-%m-%d") if hasattr(dp, "strftime") else (str(dp) if dp else "")
                dz = r.get("data_przydatnosci")
                dz_str = dz.strftime("%Y-%m-%d") if hasattr(dz, "strftime") else (str(dz) if dz else "")

                results.append({
                    "id": r["id"],
                    "nr_palety": r["nr_palety"],
                    "nazwa": r["nazwa"] or "",
                    "stan_magazynowy": float(r["stan_magazynowy"] or 0),
                    "lokalizacja": r["lokalizacja"] or "",
                    "nr_partii": r["nr_partii"] or "",
                    "data_produkcji": dp_str,
                    "data_przydatnosci": dz_str,
                    "jednostka": r.get("jednostka") or "kg",
                    "typ": "Surowiec"
                })

            return results
        except Exception:
            return []
        finally:
            conn.close()
