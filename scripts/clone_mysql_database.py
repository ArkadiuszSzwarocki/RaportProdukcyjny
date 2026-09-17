from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Dict, List, Tuple

import mysql.connector

DEFAULT_IGNORED_ROWCOUNT_TABLES = {
    "aktywne_sesje",
    "app_instance_heartbeat",
    "auto_report_history",
}


def parse_env_file(env_path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    if not env_path.exists():
        return env

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def get_db_connection(host: str, port: int, user: str, password: str, database: str | None = None):
    params = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "charset": "utf8mb4",
        "connection_timeout": 30,
    }
    if database:
        params["database"] = database
    return mysql.connector.connect(**params)


def list_tables_and_views(conn, db_name: str) -> Tuple[List[str], List[str]]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT TABLE_NAME, TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME
        """,
        (db_name,),
    )
    rows = cursor.fetchall()
    cursor.close()

    tables = [name for name, typ in rows if str(typ).upper() == "BASE TABLE"]
    views = [name for name, typ in rows if str(typ).upper() == "VIEW"]
    return tables, views


def drop_target_objects(conn, target_db: str) -> None:
    tables, views = list_tables_and_views(conn, target_db)
    cursor = conn.cursor()
    cursor.execute(f"USE `{target_db}`")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")

    for view in views:
        cursor.execute(f"DROP VIEW IF EXISTS `{view}`")

    for table in tables:
        cursor.execute(f"DROP TABLE IF EXISTS `{table}`")

    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    conn.commit()
    cursor.close()


def show_create_table(conn, db_name: str, table_name: str) -> str:
    cursor = conn.cursor()
    cursor.execute(f"SHOW CREATE TABLE `{db_name}`.`{table_name}`")
    row = cursor.fetchone()
    cursor.close()
    return row[1]


def show_create_view(conn, db_name: str, view_name: str) -> str:
    cursor = conn.cursor(dictionary=True)
    cursor.execute(f"SHOW CREATE VIEW `{db_name}`.`{view_name}`")
    row = cursor.fetchone()
    cursor.close()
    stmt = row.get("Create View") or ""
    if " DEFINER=" in stmt:
        pre, post = stmt.split(" DEFINER=", 1)
        if " VIEW " in post:
            post = post.split(" VIEW ", 1)[1]
            stmt = f"{pre} VIEW {post}"
    return stmt


def clone_tables(
    src_conn,
    dst_conn,
    source_db: str,
    target_db: str,
    batch_size: int = 250,
) -> List[str]:
    tables, _ = list_tables_and_views(src_conn, source_db)
    deduped_tables: List[str] = []
    seen_lower = set()
    for table in tables:
        key = table.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        deduped_tables.append(table)
    tables = deduped_tables
    cursor = dst_conn.cursor()

    cursor.execute(f"USE `{target_db}`")
    cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
    for table in tables:
        src_conn.ping(reconnect=True, attempts=3, delay=2)
        dst_conn.ping(reconnect=True, attempts=3, delay=2)
        cursor.execute(f"DROP VIEW IF EXISTS `{target_db}`.`{table}`")
        cursor.execute(f"DROP TABLE IF EXISTS `{target_db}`.`{table}`")
        try:
            cursor.execute(
                f"CREATE TABLE `{target_db}`.`{table}` LIKE `{source_db}`.`{table}`"
            )
        except mysql.connector.Error as exc:
            if getattr(exc, "errno", None) != 1050:
                raise
    dst_conn.commit()

    for table in tables:
        src_conn.ping(reconnect=True, attempts=3, delay=2)
        dst_conn.ping(reconnect=True, attempts=3, delay=2)
        try:
            cursor.execute(
                f"INSERT INTO `{target_db}`.`{table}` SELECT * FROM `{source_db}`.`{table}`"
            )
        except mysql.connector.Error as exc:
            if getattr(exc, "errno", None) != 1062:
                raise
        dst_conn.commit()

    cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
    dst_conn.commit()
    cursor.close()
    return tables


def clone_views(src_conn, dst_conn, source_db: str, target_db: str) -> List[str]:
    _, views = list_tables_and_views(src_conn, source_db)
    cursor = dst_conn.cursor()
    cursor.execute(f"USE `{target_db}`")

    for view in views:
        cursor.execute(f"DROP VIEW IF EXISTS `{target_db}`.`{view}`")
        cursor.execute(f"DROP TABLE IF EXISTS `{target_db}`.`{view}`")
        create_stmt = show_create_view(src_conn, source_db, view)
        if create_stmt:
            create_stmt = create_stmt.replace(
                f"`{source_db}`.",
                f"`{target_db}`.",
            )
            cursor.execute(create_stmt)

    dst_conn.commit()
    cursor.close()
    return views


def ensure_target_database(conn, target_db: str) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
        (target_db,),
    )
    exists = cursor.fetchone() is not None
    if not exists:
        cursor.execute(f"CREATE DATABASE `{target_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")
        conn.commit()
    cursor.close()


def recreate_target_database(conn, target_db: str) -> None:
    cursor = conn.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS `{target_db}`")
    cursor.execute(
        f"CREATE DATABASE `{target_db}` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
    )
    conn.commit()
    cursor.close()


def verify_source_database(conn, source_db: str) -> None:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s",
        (source_db,),
    )
    exists = cursor.fetchone() is not None
    cursor.close()
    if not exists:
        raise RuntimeError(f"Source database not found: {source_db}")


def count_rows(conn, db_name: str, table_name: str) -> int:
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM `{db_name}`.`{table_name}`")
    row = cursor.fetchone()
    cursor.close()
    return int(row[0] if row else 0)


def validate_clone(
    conn,
    source_db: str,
    target_db: str,
    row_count_check_limit: int = 10,
    ignored_rowcount_tables: set[str] | None = None,
) -> Tuple[bool, List[str]]:
    messages: List[str] = []
    ignored_tables = ignored_rowcount_tables or set()

    src_tables, src_views = list_tables_and_views(conn, source_db)
    dst_tables, dst_views = list_tables_and_views(conn, target_db)

    ok = True

    if len(src_tables) != len(dst_tables):
        ok = False
        messages.append(
            f"[ERR] Table count mismatch: source={len(src_tables)} target={len(dst_tables)}"
        )
    else:
        messages.append(f"[OK] Table count: {len(src_tables)}")

    if len(src_views) != len(dst_views):
        ok = False
        messages.append(
            f"[ERR] View count mismatch: source={len(src_views)} target={len(dst_views)}"
        )
    else:
        messages.append(f"[OK] View count: {len(src_views)}")

    src_view_set = set(src_views)
    dst_view_set = set(dst_views)
    if src_view_set != dst_view_set:
        ok = False
        missing = sorted(src_view_set - dst_view_set)
        extra = sorted(dst_view_set - src_view_set)
        if missing:
            messages.append(f"[ERR] Missing views in target: {', '.join(missing)}")
        if extra:
            messages.append(f"[ERR] Extra views in target: {', '.join(extra)}")
    else:
        messages.append("[OK] View names match")

    dst_table_set = set(dst_tables)
    common_tables = [t for t in src_tables if t in dst_table_set and t not in ignored_tables]
    sample = common_tables[: max(0, row_count_check_limit)]
    if sample:
        for table in sample:
            src_count = count_rows(conn, source_db, table)
            dst_count = count_rows(conn, target_db, table)
            if src_count != dst_count:
                ok = False
                messages.append(
                    f"[ERR] Row count mismatch in {table}: source={src_count} target={dst_count}"
                )
            else:
                messages.append(f"[OK] Row count {table}: {src_count}")

    if ignored_tables:
        messages.append(
            f"[INFO] Row-count validation ignored tables: {', '.join(sorted(ignored_tables))}"
        )

    return ok, messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Clone one MySQL database into another.")
    parser.add_argument("--source", required=True, help="Source database name")
    parser.add_argument("--target", required=True, help="Target database name")
    parser.add_argument("--env-file", default=".env", help="Path to .env file")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Skip clone and only validate source vs target",
    )
    parser.add_argument(
        "--row-count-check-limit",
        type=int,
        default=10,
        help="How many tables should be checked with row counts during validation",
    )
    parser.add_argument(
        "--ignore-row-count-table",
        action="append",
        default=[],
        help="Table name to ignore in row-count validation (can be used multiple times)",
    )
    args = parser.parse_args()

    ignored_tables = {
        *DEFAULT_IGNORED_ROWCOUNT_TABLES,
        *(name.strip() for name in args.ignore_row_count_table if name and name.strip()),
    }

    env = parse_env_file(Path(args.env_file))
    host = os.getenv("DB_HOST") or env.get("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT") or env.get("DB_PORT", "3306"))
    user = os.getenv("DB_USER") or env.get("DB_USER", "root")
    password = os.getenv("DB_PASSWORD") or env.get("DB_PASSWORD", "")

    conn = get_db_connection(host=host, port=port, user=user, password=password)
    src_conn = get_db_connection(host=host, port=port, user=user, password=password)
    dst_conn = get_db_connection(host=host, port=port, user=user, password=password)
    try:
        verify_source_database(conn, args.source)
        ensure_target_database(conn, args.target)

        if args.validate_only:
            ok, messages = validate_clone(
                conn,
                args.source,
                args.target,
                row_count_check_limit=args.row_count_check_limit,
                ignored_rowcount_tables=ignored_tables,
            )
            for line in messages:
                print(line)
            if ok:
                print("[DONE] Validation completed successfully.")
                return 0
            print("[FAIL] Validation detected mismatches.")
            return 1

        print(f"[INFO] Recreating target database: {args.target}")
        recreate_target_database(conn, args.target)

        print(f"[INFO] Cloning tables and rows: {args.source} -> {args.target}")
        tables = clone_tables(src_conn, dst_conn, args.source, args.target)
        print(f"[OK] Tables copied: {len(tables)}")

        print(f"[INFO] Cloning views: {args.source} -> {args.target}")
        views = clone_views(src_conn, dst_conn, args.source, args.target)
        print(f"[OK] Views copied: {len(views)}")

        ok, messages = validate_clone(
            conn,
            args.source,
            args.target,
            row_count_check_limit=args.row_count_check_limit,
            ignored_rowcount_tables=ignored_tables,
        )
        for line in messages:
            print(line)
        if not ok:
            print("[FAIL] Clone finished but validation detected mismatches.")
            return 1

        print("[DONE] Database clone completed successfully.")
    finally:
        conn.close()
        src_conn.close()
        dst_conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())