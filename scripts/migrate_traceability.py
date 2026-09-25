"""Idempotent migration for warehouse movement traceability."""

from pathlib import Path

import mysql.connector


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def migrate() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    env = _read_env(repo_root / ".env")
    connection = mysql.connector.connect(
        host=env.get("DB_HOST", "localhost"),
        port=int(env.get("DB_PORT", "3307")),
        database=env.get("DB_NAME", "biblioteka"),
        user=env.get("DB_USER", "biblioteka"),
        password=env.get("DB_PASSWORD", ""),
        charset="utf8mb4",
    )
    try:
        cursor = connection.cursor()
        definitions = {
            "event_id": "CHAR(36) NULL",
            "entity_type": "VARCHAR(50) NULL",
            "operation_id": "VARCHAR(100) NULL",
            "quantity_before": "DECIMAL(14,3) NULL",
            "quantity_after": "DECIMAL(14,3) NULL",
        }
        cursor.execute("SHOW COLUMNS FROM palety_historia")
        columns = {row[0] for row in cursor.fetchall()}
        for name, definition in definitions.items():
            if name not in columns:
                cursor.execute(f"ALTER TABLE palety_historia ADD COLUMN {name} {definition}")

        cursor.execute("UPDATE palety_historia SET event_id = UUID() WHERE event_id IS NULL OR event_id = ''")
        cursor.execute(
            "UPDATE palety_historia SET entity_type = typ_palety "
            "WHERE entity_type IS NULL OR entity_type = ''"
        )
        # MariaDB can populate UUIDs for legacy INSERT statements that do not yet
        # call MovementRecorder. This needs no elevated trigger privileges.
        cursor.execute(
            "ALTER TABLE palety_historia "
            "MODIFY event_id CHAR(36) NOT NULL DEFAULT (UUID())"
        )

        indexes = {
            "uq_palety_historia_event_id": "UNIQUE INDEX uq_palety_historia_event_id (event_id)",
            "idx_ph_sscc_time": "INDEX idx_ph_sscc_time (nr_palety, data_ruchu)",
            "idx_ph_operation_id": "INDEX idx_ph_operation_id (operation_id)",
        }
        cursor.execute("SHOW INDEX FROM palety_historia")
        existing_indexes = {row[2] for row in cursor.fetchall()}
        for name, definition in indexes.items():
            if name not in existing_indexes:
                cursor.execute(f"ALTER TABLE palety_historia ADD {definition}")

        cursor.execute(
            "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
            "WHERE TRIGGER_SCHEMA = DATABASE() AND TRIGGER_NAME = %s",
            ("bi_palety_historia_trace",),
        )
        if not cursor.fetchone():
            try:
                cursor.execute(
                    "CREATE TRIGGER bi_palety_historia_trace "
                    "BEFORE INSERT ON palety_historia FOR EACH ROW "
                    "SET NEW.event_id = COALESCE(NULLIF(NEW.event_id, ''), UUID()), "
                    "NEW.entity_type = COALESCE(NULLIF(NEW.entity_type, ''), NEW.typ_palety)"
                )
            except mysql.connector.Error as exc:
                if exc.errno != 1419:
                    raise
                print("Trigger skipped: database account has no required SUPER privilege.")
        connection.commit()
        print("Traceability migration completed.")
        cursor.execute(
            "SELECT COUNT(*), SUM(event_id IS NULL OR event_id = ''), "
            "SUM(entity_type IS NULL OR entity_type = '') FROM palety_historia"
        )
        total, missing_event_id, missing_entity_type = cursor.fetchone()
        duplicate_grouping = (
            "GROUP BY paleta_id, nr_palety, linia, typ_palety, akcja, "
            "lokalizacja_zrodlowa, lokalizacja_docelowa, komentarz, user_login, data_ruchu "
            "HAVING COUNT(*) > 1"
        )
        cursor.execute(
            "SELECT COALESCE(SUM(duplicate_count - 1), 0) FROM ("
            "SELECT COUNT(*) AS duplicate_count FROM palety_historia "
            f"{duplicate_grouping}) duplicates"
        )
        all_duplicate_surplus = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COALESCE(SUM(duplicate_count - 1), 0) FROM ("
            "SELECT COUNT(*) AS duplicate_count FROM palety_historia "
            "WHERE paleta_id IS NOT NULL OR NULLIF(nr_palety, '') IS NOT NULL "
            f"{duplicate_grouping}) duplicates"
        )
        definite_duplicate_surplus = cursor.fetchone()[0]
        ambiguous_duplicate_surplus = all_duplicate_surplus - definite_duplicate_surplus
        print(
            f"Verification: rows={total}, missing_event_id={missing_event_id or 0}, "
            f"missing_entity_type={missing_entity_type or 0}, "
            f"definite_exact_duplicate_surplus={definite_duplicate_surplus or 0}, "
            f"ambiguous_exact_duplicate_surplus={ambiguous_duplicate_surplus or 0}"
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    migrate()
