"""Manual AGRO batch settlement, independent of plan and measured execution."""
from decimal import Decimal, InvalidOperation
from mysql.connector import Error as DatabaseError


def ensure_zasyp_excel_schema(cursor):
    cursor.execute("SHOW COLUMNS FROM plan_produkcji_agro LIKE 'zasyp_excel_kg'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE plan_produkcji_agro ADD COLUMN zasyp_excel_kg DECIMAL(14,3) NULL DEFAULT NULL")


class ZasypExcelService:
    @staticmethod
    def parse(value):
        message = 'Podaj faktyczną masę zasypów wg Excel w kg (liczba nieujemna, do 3 miejsc po przecinku).'
        try:
            if value is None or not str(value).strip():
                raise ValueError(message)
            amount = Decimal(str(value).replace(' ', '').replace('\u00a0', '').replace(',', '.'))
            if not amount.is_finite() or amount < 0 or amount > Decimal('99999999999.999'):
                raise ValueError(message)
            precise = amount.quantize(Decimal('0.001'))
            if precise != amount:
                raise ValueError(message)
            return precise
        except (InvalidOperation, TypeError):
            raise ValueError(message) from None

    @staticmethod
    def for_work_orders(connection, order_ids):
        ids = list(dict.fromkeys(int(value) for value in order_ids if value is not None))
        if not ids:
            return {}
        cursor = connection.cursor(dictionary=True)
        try:
            # Legacy fallback requires exactly one source batch; never guess between orders.
            placeholders = ','.join(['%s'] * len(ids))
            cursor.execute(f"""
                SELECT w.id,
                  CASE WHEN COALESCE(w.zasyp_id, 0) > 0 THEN z.zasyp_excel_kg ELSE (
                    SELECT CASE WHEN COUNT(*) = 1 THEN MAX(s.zasyp_excel_kg) ELSE NULL END
                    FROM plan_produkcji_agro s
                    WHERE s.sekcja = 'Zasyp' AND COALESCE(s.is_deleted, 0) = 0
                      AND LOWER(TRIM(s.produkt)) = LOWER(TRIM(w.produkt))
                      AND DATE(s.data_planu) = DATE(w.data_planu)
                  ) END AS zasyp_excel_kg
                FROM plan_produkcji_agro w
                LEFT JOIN plan_produkcji_agro z ON z.id = w.zasyp_id
                  AND z.sekcja = 'Zasyp' AND COALESCE(z.is_deleted, 0) = 0
                WHERE w.id IN ({placeholders}) AND w.sekcja IN ('Workowanie', 'Czyszczenie')
            """, tuple(ids))
            return {row['id']: row['zasyp_excel_kg'] for row in cursor.fetchall()}
        except DatabaseError as error:
            # The report remains readable during deployment before the additive migration.
            if error.errno == 1054 and 'zasyp_excel_kg' in str(error):
                return {}
            raise
        finally:
            cursor.close()
