class HistoryIndexer:
    _columns_cache: dict[str, set[str]] = {}
    _indexes_checked: bool = False

    @classmethod
    def get_table_columns(cls, cursor, table_name: str) -> set[str]:
        """Safely fetch existing column names in lowercase for a given table with in-memory caching."""
        if table_name in cls._columns_cache:
            return cls._columns_cache[table_name]
        try:
            cursor.execute(f"SHOW COLUMNS FROM {table_name}")
            rows = cursor.fetchall()
            cols = set()
            for r in rows:
                if isinstance(r, dict):
                    cols.add(str(r.get('Field') or '').lower())
                else:
                    cols.add(str(r[0] or '').lower())
            cls._columns_cache[table_name] = cols
            return cols
        except Exception as e:
            print(f"[WarehouseHistoryService] SHOW COLUMNS error for {table_name}: {e}")
            return set()

    @classmethod
    def ensure_performance_indexes(cls, cursor, conn):
        """Ensure critical database indexes exist once during application lifetime without repeating DDL overhead."""
        if cls._indexes_checked:
            return
        cls._indexes_checked = True

        def safe_add_index(table: str, idx_name: str, col_expr: str):
            try:
                cursor.execute(f"SHOW INDEX FROM {table} WHERE Key_name = %s", (idx_name,))
                if not cursor.fetchall():
                    cursor.execute(f"CREATE INDEX {idx_name} ON {table} ({col_expr})")
                    conn.commit()
            except Exception:
                pass

        safe_add_index('palety_historia', 'idx_ph_data_ruchu', 'data_ruchu')
        safe_add_index('palety_historia', 'idx_ph_paleta_id', 'paleta_id')
        safe_add_index('palety_historia', 'idx_ph_nr_palety', 'nr_palety')
        safe_add_index('magazyn_archiwum', 'idx_arch_orig_id', 'original_id')
        safe_add_index('magazyn_archiwum', 'idx_arch_nr_palety', 'nr_palety')
