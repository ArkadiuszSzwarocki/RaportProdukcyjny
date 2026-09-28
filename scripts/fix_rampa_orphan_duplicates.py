"""Archive verified RAMPA duplicates and relink completed delivery items."""

import json
from pathlib import Path

import mysql.connector


DELIVERY_IDS = (
    "64ebaa3c-167d-474b",  # Cargill / Hydro
    "33992405-cd54-4a46",  # ZORINA / SWP
)
EXPECTED_COUNTS = {
    "64ebaa3c-167d-474b": 24,
    "33992405-cd54-4a46": 23,
}


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def fix() -> None:
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
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, status, items FROM magazyn_dostawy WHERE id IN (%s, %s) FOR UPDATE",
            DELIVERY_IDS,
        )
        deliveries = {row["id"]: row for row in cursor.fetchall()}
        if set(deliveries) != set(DELIVERY_IDS):
            raise RuntimeError("Nie znaleziono obu oczekiwanych dostaw.")

        corrections = []
        corrected_items_by_delivery = {}
        for delivery_id in DELIVERY_IDS:
            delivery = deliveries[delivery_id]
            if str(delivery.get("status") or "").upper() != "COMPLETED":
                raise RuntimeError(f"Dostawa {delivery_id} nie jest zakończona.")
            items = json.loads(delivery.get("items") or "[]")
            if len(items) != EXPECTED_COUNTS[delivery_id]:
                raise RuntimeError(f"Dostawa {delivery_id} ma nieoczekiwaną liczbę pozycji: {len(items)}.")

            for item in items:
                if not item.get("accepted") or item.get("rejected"):
                    raise RuntimeError(f"Pozycja {item.get('id')} nie jest jednoznacznie przyjęta.")
                orphan_id = item.get("sourcePalletId")
                physical_sscc = str(item.get("nr_palety") or "").strip()
                if not orphan_id or not physical_sscc:
                    raise RuntimeError(f"Pozycja {item.get('id')} nie ma powiązania lub SSCC.")

                cursor.execute(
                    "SELECT * FROM magazyn_surowce WHERE id = %s FOR UPDATE",
                    (orphan_id,),
                )
                orphan = cursor.fetchone()
                if not orphan:
                    raise RuntimeError(f"Brak rekordu źródłowego {orphan_id}.")
                if str(orphan.get("lokalizacja") or "").upper() != "RAMPA":
                    raise RuntimeError(f"Rekord {orphan_id} nie znajduje się na RAMPA.")
                if float(orphan.get("stan_magazynowy") or 0) <= 0:
                    raise RuntimeError(f"Rekord {orphan_id} nie ma aktywnego stanu.")

                cursor.execute(
                    "SELECT * FROM magazyn_surowce "
                    "WHERE nr_palety = %s AND id <> %s AND stan_magazynowy > 0 FOR UPDATE",
                    (physical_sscc, orphan_id),
                )
                physical_rows = cursor.fetchall()
                if len(physical_rows) != 1:
                    raise RuntimeError(
                        f"SSCC {physical_sscc}: oczekiwano jednej palety fizycznej, znaleziono {len(physical_rows)}."
                    )
                physical = physical_rows[0]
                if str(physical.get("lokalizacja") or "").upper() == "RAMPA":
                    raise RuntimeError(f"Paleta fizyczna {physical_sscc} nadal jest na RAMPA.")

                corrections.append((delivery_id, item, orphan, physical))
                item["sourcePalletId"] = physical["id"]
                item["sourcePalletNo"] = physical_sscc
            corrected_items_by_delivery[delivery_id] = items

        if len(corrections) != 47:
            raise RuntimeError(f"Oczekiwano 47 korekt, przygotowano {len(corrections)}.")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_rampa_duplicates_20260925 AS
            SELECT s.*, CAST(NULL AS CHAR(36)) AS delivery_id,
                   CAST(NULL AS SIGNED) AS physical_pallet_id,
                   CAST(NULL AS CHAR(100)) AS physical_sscc,
                   CAST(NULL AS DATETIME) AS archived_at,
                   CAST(NULL AS CHAR(100)) AS archived_by
            FROM magazyn_surowce s WHERE 1 = 0
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_rampa_delivery_items_20260925 (
                delivery_id VARCHAR(64) PRIMARY KEY,
                items_before LONGTEXT NOT NULL,
                corrected_at DATETIME NOT NULL,
                corrected_by VARCHAR(100) NOT NULL
            )
        """)

        for delivery_id, delivery in deliveries.items():
            cursor.execute(
                "INSERT IGNORE INTO audit_rampa_delivery_items_20260925 "
                "(delivery_id, items_before, corrected_at, corrected_by) VALUES (%s, %s, NOW(), %s)",
                (delivery_id, delivery["items"], "codex-audit"),
            )

        for delivery_id, item, orphan, physical in corrections:
            cursor.execute(
                "SELECT 1 FROM audit_rampa_duplicates_20260925 WHERE id = %s LIMIT 1",
                (orphan["id"],),
            )
            if not cursor.fetchone():
                columns = list(orphan.keys())
                cursor.execute(
                    f"INSERT INTO audit_rampa_duplicates_20260925 "
                    f"({', '.join(f'`{column}`' for column in columns)}, delivery_id, physical_pallet_id, "
                    "physical_sscc, archived_at, archived_by) "
                    f"VALUES ({', '.join(['%s'] * len(columns))}, %s, %s, %s, NOW(), %s)",
                    tuple(orphan[column] for column in columns)
                    + (delivery_id, physical["id"], physical["nr_palety"], "codex-audit"),
                )

            cursor.execute(
                "UPDATE magazyn_surowce SET stan_magazynowy = 0, lokalizacja = %s, "
                "is_blocked = 1, updated_at = NOW() WHERE id = %s",
                ("ARCHIWUM_DUPLIKAT", orphan["id"]),
            )
            operation_id = f"cleanup-rampa-20260925:{orphan['id']}"
            cursor.execute(
                "INSERT INTO palety_historia "
                "(paleta_id, nr_palety, linia, typ_palety, entity_type, operation_id, akcja, "
                "lokalizacja_zrodlowa, lokalizacja_docelowa, quantity_before, quantity_after, "
                "komentarz, user_login, data_ruchu) "
                "SELECT %s, %s, 'PSD', 'surowiec', 'surowiec', %s, 'ARCHIWIZACJA_DUPLIKAT', "
                "'RAMPA', 'ARCHIWUM_DUPLIKAT', %s, 0, %s, 'codex-audit', NOW() "
                "WHERE NOT EXISTS (SELECT 1 FROM palety_historia WHERE operation_id = %s)",
                (
                    orphan["id"], orphan.get("nr_palety"), operation_id,
                    orphan.get("stan_magazynowy"),
                    f"Duplikat po zakończonej dostawie {delivery_id}; właściwa paleta: {physical['nr_palety']} (ID {physical['id']})",
                    operation_id,
                ),
            )

        for delivery_id, items in corrected_items_by_delivery.items():
            cursor.execute(
                "UPDATE magazyn_dostawy SET items = %s WHERE id = %s",
                (json.dumps(items, ensure_ascii=False), delivery_id),
            )

        connection.commit()
        print(f"Archived {len(corrections)} verified RAMPA duplicates and relinked {len(deliveries)} deliveries.")
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


if __name__ == "__main__":
    fix()
