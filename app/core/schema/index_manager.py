"""Composite index generator for dashboard and WMS query optimization."""
from __future__ import annotations


class IndexManager:
    """Manages creation of composite performance indexes."""

    @staticmethod
    def create_composite_indexes(cursor):
        indexes_to_create = [
            ("plan_produkcji", "idx_pp_data_status_sekcja", "(data_planu, status, sekcja)"),
            ("plan_produkcji_agro", "idx_ppa_data_status", "(data_planu, status)"),
            ("palety_workowanie", "idx_pw_plan_status", "(plan_id, status)"),
            ("palety_agro", "idx_pa_plan_status", "(plan_id, status)"),
            ("szarze", "idx_sz_plan_status", "(plan_id, status)"),
            ("szarze_agro", "idx_sza_plan_status", "(plan_id, status)"),
            ("magazyn_surowce", "idx_ms_nazwa_stan", "(nazwa(50), stan_magazynowy)"),
            ("magazyn_opakowania", "idx_mo_nazwa_stan", "(nazwa(50), stan_magazynowy)"),
            ("magazyn_palety", "idx_mp_produkt_waga", "(produkt(50), waga_netto)"),
            ("magazyn_palety_agro", "idx_mpa_produkt_waga", "(produkt(50), waga_netto)"),
        ]
        for table, index_name, columns in indexes_to_create:
            try:
                cursor.execute(f"CREATE INDEX {index_name} ON {table} {columns}")
            except Exception:
                pass
