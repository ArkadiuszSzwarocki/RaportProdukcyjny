#!/usr/bin/env python3
"""
Usuwa błędne szarże (gdzie waga = tonaz planu) i synchronizuje tonaz_rzeczywisty.
Błędne szarże to takie, które były skopiowane z pola tonaz zamiast być rzeczywistymi szarżami.
"""

import argparse
from db import get_db_connection


def parse_args():
    parser = argparse.ArgumentParser(
        description="Usuwa błędne szarże (gdzie waga = tonaz) i synchronizuje tonaz_rzeczywisty."
    )
    parser.add_argument("--plan-id", type=int, help="Czyść konkretny plan (id).")
    parser.add_argument(
        "--date",
        help="Czyść wszystkie plany na dany dzień (format RRRR-MM-DD).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nie zapisuj zmian, pokaż tylko co by zostało usunięte.",
    )
    return parser.parse_args()


def clean_and_sync(plan_id: int | None, date: str | None, dry_run: bool) -> tuple[int, int]:
    """
    Usuwa błędne szarże i synchronizuje tonaz_rzeczywisty.
    Zwraca (liczba usuniętych szarż, liczba zsynchronizowanych planów)
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # Znajdź błędne szarże (gdzie waga = tonaz planu)
    where_parts = ["p.sekcja = 'Zasyp'"]
    params: list[object] = []
    
    if plan_id is not None:
        where_parts.append("p.id = %s")
        params.append(plan_id)
    if date is not None:
        where_parts.append("DATE(p.data_planu) = %s")
        params.append(date)

    where_clause = " AND ".join(where_parts)

    # Znajdź szarże, które są równe tonaz planu (błędne duplikaty)
    query_find = f"""
        SELECT sz.id, sz.plan_id, sz.waga, p.tonaz
        FROM szarze sz
        INNER JOIN plan_produkcji p ON sz.plan_id = p.id
        WHERE {where_clause} AND sz.waga = p.tonaz
    """
    
    cursor.execute(query_find, params)
    bad_szarze = cursor.fetchall()
    deleted_count = 0
    
    if bad_szarze:
        print(f"\nBłędne szarże (waga = tonaz planu):")
        for szarza_id, plan_id_row, waga, tonaz in bad_szarze:
            print(f"  Szarża ID={szarza_id}, plan_id={plan_id_row}, waga={waga} (= tonaz={tonaz})")
            if not dry_run:
                cursor.execute("DELETE FROM szarze WHERE id = %s", (szarza_id,))
                deleted_count += 1
    
    if not dry_run and deleted_count > 0:
        conn.commit()
        print(f"✓ Usunięto {deleted_count} błędnych szarż")
    
    # Teraz synchronizuj tonaz_rzeczywisty dla wszystkich planów w zakresie
    print(f"\nSynchronizowanie tonaz_rzeczywisty...")
    
    query_sync = f"""
        SELECT
            p.id,
            COALESCE(SUM(sz.waga), 0) AS szarze_sum,
            COALESCE(p.tonaz_rzeczywisty, 0) AS current_realization
        FROM plan_produkcji p
        LEFT JOIN szarze sz ON sz.plan_id = p.id
        WHERE {where_clause}
        GROUP BY p.id, p.tonaz_rzeczywisty
    """
    
    cursor.execute(query_sync, params)
    synced_count = 0
    
    for plan_id_row, szarze_sum, current_real in cursor.fetchall():
        if abs(szarze_sum - current_real) > 0.001:  # Jest różnica
            print(f"  Plan {plan_id_row}: {current_real:.2f} kg → {szarze_sum:.2f} kg")
            if not dry_run:
                cursor.execute(
                    "UPDATE plan_produkcji SET tonaz_rzeczywisty = %s WHERE id = %s",
                    (szarze_sum, plan_id_row),
                )
                synced_count += 1
    
    if not dry_run:
        conn.commit()
        print(f"✓ Zsynchronizowano {synced_count} planów")
    
    cursor.close()
    conn.close()
    
    return deleted_count, synced_count


def main() -> None:
    args = parse_args()
    
    print("=" * 60)
    print("Czyszczenie błędnych szarż i synchronizacja")
    print("=" * 60)
    
    if args.dry_run:
        print("[DRY RUN MODE - bez zapisywania zmian]\n")
    
    try:
        deleted, synced = clean_and_sync(args.plan_id, args.date, args.dry_run)
    except Exception as e:
        print(f"❌ Błąd: {e}")
        raise SystemExit(1)
    
    print("\n" + "=" * 60)
    if args.dry_run:
        print("Dry run – nie zapisano zmian.")
        print(f"Znaleziono do usunięcia: {deleted} szarż")
        print(f"Do zsynchronizowania: {synced} planów")
    else:
        print(f"✓ Zakończono: usunięto {deleted} szarż, zsynchronizowano {synced} planów")
    print("=" * 60)


if __name__ == "__main__":
    main()
