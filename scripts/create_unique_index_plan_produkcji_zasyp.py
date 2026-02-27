#!/usr/bin/env python3
"""
Skrypt migracyjny: usuwa duplikaty `plan_produkcji` w sekcji 'Workowanie'
powiązane z tym samym `zasyp_id`, przemapowuje `palety_workowanie.plan_id`
i tworzy unikatowy indeks na `plan_produkcji(zasyp_id)`.

Uwaga: domyślnie skrypt tylko raportuje co by zrobił. Aby wykonać zmiany,
uruchom z flagą `--apply` lub ustaw zmienną środowiskową `APPLY=1`.

Przykład:
    python scripts/create_unique_index_plan_produkcji_zasyp.py --apply
"""
import os
import argparse
from app.db import get_db_connection


def find_duplicates(cursor):
    cursor.execute("""
        SELECT zasyp_id, COUNT(*) as cnt
        FROM plan_produkcji
        WHERE sekcja = 'Workowanie' AND zasyp_id IS NOT NULL
        GROUP BY zasyp_id
        HAVING cnt > 1
    """)
    return cursor.fetchall()


def cleanup_duplicates(conn, apply=False):
    cursor = conn.cursor()
    duplicates = find_duplicates(cursor)
    if not duplicates:
        print('[OK] Nie znaleziono duplikatów Workowanie powiązanych z tym samym zasyp_id')
        return

    print(f'[INFO] Znaleziono {len(duplicates)} zasyp_id z więcej niż jednym Workowaniem')

    for zasyp_id, cnt in duplicates:
        print(f'-> zasyp_id={zasyp_id} ma {cnt} wpisów')
        cursor.execute("SELECT id, data_planu, status, tonaz, nazwa_zlecenia FROM plan_produkcji WHERE sekcja = %s AND zasyp_id = %s ORDER BY id ASC", ('Workowanie', zasyp_id))
        rows = cursor.fetchall()
        if not rows:
            continue
        keeper_id = rows[0][0]
        other_ids = [r[0] for r in rows[1:]]
        print(f'  -> zachowaj id={keeper_id}, do usunięcia: {other_ids}')

        if apply:
            # Reassign palety_workowanie.plan_id to keeper
            for oid in other_ids:
                print(f'    - Przypisuję palety z plan_id={oid} do plan_id={keeper_id}')
                cursor.execute('UPDATE palety_workowanie SET plan_id=%s WHERE plan_id=%s', (keeper_id, oid))

            # Delete duplicate plan_produkcji rows
            for oid in other_ids:
                print(f'    - Usuwam plan_produkcji id={oid}')
                cursor.execute('DELETE FROM plan_produkcji WHERE id=%s', (oid,))

    if apply:
        conn.commit()
        print('[OK] Deduplicacja wykonana i zatwierdzona')
    else:
        print('[DRY RUN] Nie wprowadzono zmian. Uruchom z --apply aby zastosować.')


def create_unique_index(conn, apply=False):
    cursor = conn.cursor()
    # Check if index already exists
    cursor.execute("SHOW INDEX FROM plan_produkcji WHERE Column_name = 'zasyp_id'")
    existing = cursor.fetchall()
    if existing:
        print('[WARN] Istnieją indeksy na kolumnie zasyp_id; sprawdź ręcznie przed dodaniem unikatowego indeksu')
        for row in existing:
            print('  ', row)
        # continue to attempt creation but be cautious

    sql = "ALTER TABLE plan_produkcji ADD UNIQUE INDEX uq_plan_produkcji_zasyp_id (zasyp_id)"
    print(f"[INFO] Polecenie tworzenia indeksu: {sql}")
    if apply:
        try:
            cursor.execute(sql)
            conn.commit()
            print('[OK] Utworzono unikatowy indeks uq_plan_produkcji_zasyp_id')
        except Exception as e:
            conn.rollback()
            print(f'[ERROR] Nie udało się utworzyć indeksu: {e}')
            raise
    else:
        print('[DRY RUN] Indeks nie został utworzony. Użyj --apply, aby utworzyć indeks.')


def main():
    parser = argparse.ArgumentParser(description='Deduplikacja Workowanie i stworzenie unikatowego indeksu (zasyp_id)')
    parser.add_argument('--apply', action='store_true', help='Wykonaj zmiany (domyślnie: tylko podgląd)')
    args = parser.parse_args()
    apply = args.apply or os.environ.get('APPLY') == '1'

    conn = get_db_connection()
    try:
        cleanup_duplicates(conn, apply=apply)
        create_unique_index(conn, apply=apply)
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == '__main__':
    main()
