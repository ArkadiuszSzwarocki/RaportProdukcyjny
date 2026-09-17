from __future__ import annotations

import argparse
import os
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import mysql.connector


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


def sql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def sql_literal(value) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, datetime):
        return f"'{value.isoformat(sep=' ')}'"
    if isinstance(value, (date, time)):
        return f"'{value.isoformat()}'"
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    return f"'{sql_escape(str(value))}'"


def get_tables_and_views(cursor) -> Tuple[List[str], List[str]]:
    cursor.execute("SHOW FULL TABLES")
    base_tables: List[str] = []
    views: List[str] = []
    for row in cursor.fetchall():
        name = row[0]
        obj_type = str(row[1]).upper()
        if obj_type == "BASE TABLE":
            base_tables.append(name)
        elif obj_type == "VIEW":
            views.append(name)
    return base_tables, views


def dump_table_schema(cursor, table_name: str, out) -> None:
    cursor.execute(f"SHOW CREATE TABLE `{table_name}`")
    _, create_stmt = cursor.fetchone()
    out.write(f"--\n-- Table structure for `{table_name}`\n--\n")
    out.write(f"DROP TABLE IF EXISTS `{table_name}`;\n")
    out.write(create_stmt + ";\n\n")


def dump_view_schema(cursor, view_name: str, out) -> None:
    cursor.execute(f"SHOW CREATE VIEW `{view_name}`")
    row = cursor.fetchone()
    create_stmt = row.get("Create View") if isinstance(row, dict) else row[1]
    out.write(f"--\n-- View structure for `{view_name}`\n--\n")
    out.write(f"DROP VIEW IF EXISTS `{view_name}`;\n")
    out.write(create_stmt + ";\n\n")


def chunked(iterable: List[Tuple], size: int) -> Iterable[List[Tuple]]:
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


def dump_table_data(cursor, table_name: str, out, insert_chunk: int = 500) -> None:
    cursor.execute(f"SELECT * FROM `{table_name}`")
    rows = cursor.fetchall()
    if not rows:
        return

    columns = [f"`{col[0]}`" for col in cursor.description]
    col_list = ", ".join(columns)

    out.write(f"--\n-- Dumping data for table `{table_name}`\n--\n")
    for part in chunked(rows, insert_chunk):
        values_sql = []
        for row in part:
            row_values = ", ".join(sql_literal(v) for v in row)
            values_sql.append(f"({row_values})")
        out.write(
            f"INSERT INTO `{table_name}` ({col_list}) VALUES\n"
            + ",\n".join(values_sql)
            + ";\n"
        )
    out.write("\n")


def database_exists(cursor, db_name: str) -> bool:
    cursor.execute("SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s", (db_name,))
    return cursor.fetchone() is not None


def dump_database(host: str, port: int, user: str, password: str, db_name: str, output_path: Path) -> None:
    conn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
        charset="utf8mb4",
    )
    try:
        cursor_tables = conn.cursor()
        cursor_dict = conn.cursor(dictionary=True)

        tables, views = get_tables_and_views(cursor_tables)

        with output_path.open("w", encoding="utf-8", newline="\n") as out:
            out.write(f"-- Backup of database `{db_name}`\n")
            out.write(f"-- Generated at {datetime.now().isoformat(sep=' ', timespec='seconds')}\n\n")
            out.write("SET FOREIGN_KEY_CHECKS=0;\n")
            out.write("SET SQL_MODE='NO_AUTO_VALUE_ON_ZERO';\n\n")

            for table in tables:
                dump_table_schema(cursor_tables, table, out)

            for table in tables:
                dump_table_data(cursor_tables, table, out)

            for view in views:
                dump_view_schema(cursor_dict, view, out)

            out.write("SET FOREIGN_KEY_CHECKS=1;\n")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup selected MySQL databases to .sql files.")
    parser.add_argument("--databases", nargs="+", required=True, help="Database names to backup.")
    parser.add_argument("--output-dir", default="backups", help="Directory for .sql dump files.")
    parser.add_argument("--env-file", default=".env", help="Path to .env with DB config.")
    args = parser.parse_args()

    env_vals = parse_env_file(Path(args.env_file))

    host = os.getenv("DB_HOST") or env_vals.get("DB_HOST", "localhost")
    port = int(os.getenv("DB_PORT") or env_vals.get("DB_PORT", "3306"))
    user = os.getenv("DB_USER") or env_vals.get("DB_USER", "root")
    password = os.getenv("DB_PASSWORD") or env_vals.get("DB_PASSWORD", "")

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    meta_conn = mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
    )
    try:
        meta_cursor = meta_conn.cursor()
        for db_name in args.databases:
            if not database_exists(meta_cursor, db_name):
                print(f"[WARN] Database not found, skipping: {db_name}")
                continue

            output_path = out_dir / f"db_dump_{db_name}_{timestamp}.sql"
            print(f"[INFO] Creating backup: {output_path}")
            dump_database(host, port, user, password, db_name, output_path)
            print(f"[OK] Backup completed: {db_name}")
    finally:
        meta_conn.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())