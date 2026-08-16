import argparse
from datetime import datetime

from db import get_db_connection


def parse_args():
    parser = argparse.ArgumentParser(
        description="Synchronizuje pole tonaz_rzeczywisty planu Zasyp z sumą wagi z tabeli szarze."
    )
    parser.add_argument("--plan-id", type=int, help="Zaktualizuj konkretny plan (id).")
    parser.add_argument(
        "--date",
        help="Zaktualizuj wszystkie plany na dany dzień (format RRRR-MM-DD).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nie zapisuj zmian, pokaż tylko różnice.",
    )
    return parser.parse_args()


def sync_plans(plan_id: int | None, date: str | None, dry_run: bool) -> int:
    where = ["p.sekcja = 'Zasyp'"]
    params: list[object] = []
    if plan_id is not None:
        where.append("p.id = %s")
        params.append(plan_id)
    if date is not None:
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Niepoprawny format daty: {exc}")
        where.append("DATE(p.data_planu) = %s")
        params.append(date)

    query = f"""
        SELECT
            p.id,
            COALESCE(SUM(sz.waga), 0) AS szarze_sum,
            COALESCE(p.tonaz_rzeczywisty, 0) AS current_realization
        FROM plan_produkcji p
        LEFT JOIN szarze sz ON sz.plan_id = p.id
        WHERE {' AND '.join(where)}
        GROUP BY p.id, p.tonaz_rzeczywisty
    """

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(query, params)
    updates = 0
    for plan_id_row, szarze_sum, current_real in cursor.fetchall():
        if abs(szarze_sum - current_real) < 0.001:
            continue
        print(
            f"Plan {plan_id_row}: tonaz_rzeczywisty={current_real:.2f}, suma szarż={szarze_sum:.2f}"
        )
        if not dry_run:
            cursor.execute(
                "UPDATE plan_produkcji SET tonaz_rzeczywisty = %s WHERE id = %s",
                (szarze_sum, plan_id_row),
            )
            updates += 1
    if not dry_run:
        conn.commit()
    cursor.close()
    conn.close()
    return updates


def main() -> None:
    args = parse_args()
    try:
        updated = sync_plans(args.plan_id, args.date, args.dry_run)
    except ValueError as exc:
        raise SystemExit(exc)
    if args.dry_run:
        print("Dry run – nie zapisano zmian.")
    else:
        print(f"Zaktualizowano {updated} planów.")


if __name__ == "__main__":
    main()
