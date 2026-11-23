# cspell:words TINYINT
"""Persistent, database-scoped packaging shortage notifications."""
import os
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.db import get_db_connection

SCHEMA = [
    """CREATE TABLE IF NOT EXISTS packaging_alert_groups (
        id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(100) NOT NULL,
        recipients TEXT NOT NULL, cc_recipients TEXT NULL) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
    """CREATE TABLE IF NOT EXISTS packaging_alert_rules (
        id INT AUTO_INCREMENT PRIMARY KEY, material VARCHAR(255) NOT NULL,
        stock_type VARCHAR(32) NOT NULL DEFAULT 'packaging',
        minimum DECIMAL(14,3) NOT NULL, unit VARCHAR(20) NOT NULL,
        group_id INT NULL DEFAULT NULL, enabled TINYINT NOT NULL DEFAULT 0,
        notified TINYINT NOT NULL DEFAULT 0, sent_at DATETIME NULL,
        checked_at DATETIME NULL, next_attempt DATETIME NULL, last_error TEXT NULL,
        UNIQUE KEY material_type_unique (material, stock_type),
        FOREIGN KEY (group_id) REFERENCES packaging_alert_groups(id))
        ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


STOCK_TYPE_RAW = 'raw_material'
STOCK_TYPE_ADDITIVE = 'additive'
STOCK_TYPE_PACKAGING = 'packaging'
STOCK_TYPE_FINISHED = 'finished_good'
VALID_STOCK_TYPES = (STOCK_TYPE_RAW, STOCK_TYPE_ADDITIVE, STOCK_TYPE_PACKAGING, STOCK_TYPE_FINISHED)
PACKAGING_UNITS = ('szt.', 'rolki', 'm')
STOCK_TYPE_LABELS = {
    STOCK_TYPE_RAW: 'Surowce',
    STOCK_TYPE_ADDITIVE: 'Dodatki',
    STOCK_TYPE_PACKAGING: 'Opakowania / Taśmy',
    STOCK_TYPE_FINISHED: 'Wyroby gotowe',
}
CATEGORY_TO_STOCK_TYPE = {
    'surowce': STOCK_TYPE_RAW,
    'dodatki': STOCK_TYPE_ADDITIVE,
    'taśmy': STOCK_TYPE_PACKAGING,
    'tasmy': STOCK_TYPE_PACKAGING,
    'opakowania': STOCK_TYPE_PACKAGING,
    'opakowania / taśmy': STOCK_TYPE_PACKAGING,
    'wyroby gotowe': STOCK_TYPE_FINISHED,
}


def normalize_material_key(value) -> str:
    """Normalize material names for whitespace- and case-insensitive matching."""
    return str(value or '').strip().casefold()


def normalize_stock_type(value, unit='') -> str:
    """Normalize a stock domain identifier or UI category into a canonical stock_type."""
    raw = str(value or '').strip().casefold()
    if raw in VALID_STOCK_TYPES:
        return raw
    if raw in CATEGORY_TO_STOCK_TYPE:
        return CATEGORY_TO_STOCK_TYPE[raw]
    if not raw and str(unit or '').strip().casefold() in PACKAGING_UNITS:
        return STOCK_TYPE_PACKAGING
    return ''


def make_stock_key(stock_type, material_name) -> tuple:
    """Build the composite (stock_type, normalized_material_name) lookup key."""
    return (str(stock_type or '').strip().casefold(), normalize_material_key(material_name))


def format_rule_key(stock_type, material_name) -> str:
    """Serialize a composite stock key for UI templates and DOM data attributes."""
    normalized_type, normalized_name = make_stock_key(stock_type, material_name)
    return f'{normalized_type}::{normalized_name}'


def stock_type_label(stock_type, category=None) -> str:
    """Return a human-readable Polish domain label for the given stock type."""
    if category:
        return category
    return STOCK_TYPE_LABELS.get(stock_type, 'Pozostałe')


def resolve_rule_stock_type(rule, stocks_by_key=None) -> str:
    """Determine the canonical stock_type for an alert rule, with legacy fallback."""
    resolved = normalize_stock_type(rule.get('stock_type') or rule.get('category'), unit=rule.get('unit'))
    if resolved:
        return resolved
    mat_key = normalize_material_key(rule.get('material'))
    if stocks_by_key:
        for candidate in (STOCK_TYPE_RAW, STOCK_TYPE_ADDITIVE, STOCK_TYPE_FINISHED):
            if (candidate, mat_key) in stocks_by_key:
                return candidate
    return STOCK_TYPE_RAW


def ensure_schema(connection):
    cursor = connection.cursor()
    try:
        for statement in SCHEMA:
            cursor.execute(statement)
        cursor.execute("SHOW COLUMNS FROM packaging_alert_groups LIKE 'cc_recipients'")
        if not cursor.fetchall():
            cursor.execute('ALTER TABLE packaging_alert_groups ADD COLUMN cc_recipients TEXT NULL')

        cursor.execute("SHOW COLUMNS FROM packaging_alert_rules LIKE 'group_id'")
        group_columns = cursor.fetchall() or []
        if group_columns:
            col = group_columns[0]
            is_nullable = (col.get('Null') if isinstance(col, dict) else col[2]) == 'YES'
            if not is_nullable:
                cursor.execute('ALTER TABLE packaging_alert_rules MODIFY COLUMN group_id INT NULL DEFAULT NULL')

        cursor.execute("SHOW COLUMNS FROM packaging_alert_rules LIKE 'stock_type'")
        added_stock_type = False
        if not cursor.fetchall():
            cursor.execute(
                "ALTER TABLE packaging_alert_rules ADD COLUMN stock_type VARCHAR(32) NOT NULL DEFAULT '' AFTER material"
            )
            added_stock_type = True

        cursor.execute(
            "UPDATE packaging_alert_rules SET stock_type = %s "
            "WHERE COALESCE(TRIM(stock_type), '') = '' AND unit IN ('szt.', 'rolki', 'm')",
            (STOCK_TYPE_PACKAGING,),
        )
        cursor.execute(
            "SELECT id, material, unit FROM packaging_alert_rules WHERE COALESCE(TRIM(stock_type), '') = ''"
        )
        untyped_rows = cursor.fetchall() or []
        if untyped_rows:
            dict_cursor = connection.cursor(dictionary=True)
            try:
                stocks_by_key = {
                    make_stock_key(row['stock_type'], row['material']): row['stock']
                    for row in catalog(dict_cursor)
                }
            finally:
                dict_cursor.close()
            for row in untyped_rows:
                rule_id, raw_mat, raw_unit = (
                    (row['id'], row['material'], row['unit']) if isinstance(row, dict) else (row[0], row[1], row[2])
                )
                resolved = resolve_rule_stock_type({'material': raw_mat, 'unit': raw_unit}, stocks_by_key)
                cursor.execute("UPDATE packaging_alert_rules SET stock_type = %s WHERE id = %s", (resolved, rule_id))

        if added_stock_type:
            cursor.execute(
                "ALTER TABLE packaging_alert_rules MODIFY COLUMN stock_type VARCHAR(32) NOT NULL DEFAULT 'packaging'"
            )

        cursor.execute("SHOW INDEX FROM packaging_alert_rules WHERE Key_name = 'material_type_unique'")
        if not cursor.fetchall():
            cursor.execute("ALTER TABLE packaging_alert_rules ADD UNIQUE KEY material_type_unique (material, stock_type)")
        cursor.execute("SHOW INDEX FROM packaging_alert_rules WHERE Key_name = 'material_unique'")
        if cursor.fetchall():
            cursor.execute("ALTER TABLE packaging_alert_rules DROP INDEX material_unique")

        cursor.execute(
            "SELECT id, material, stock_type FROM packaging_alert_rules "
            "WHERE CHAR_LENGTH(material) != CHAR_LENGTH(TRIM(material))"
        )
        for row in cursor.fetchall() or []:
            rule_id, raw_material, raw_stock_type = (
                (row['id'], row['material'], row['stock_type'])
                if isinstance(row, dict)
                else (row[0], row[1], row[2])
            )
            trimmed = str(raw_material or '').strip()
            if not trimmed:
                continue
            cursor.execute(
                "SELECT id FROM packaging_alert_rules WHERE material = %s AND stock_type = %s AND id <> %s LIMIT 1",
                (trimmed, raw_stock_type, rule_id),
            )
            if not cursor.fetchone():
                cursor.execute(
                    "UPDATE packaging_alert_rules SET material = %s WHERE id = %s",
                    (trimmed, rule_id),
                )
        connection.commit()
    finally:
        cursor.close()


def parse_recipients(value, optional=False):
    if optional and not str(value or "").strip():
        return []
    addresses = list(dict.fromkeys(x.strip().lower() for x in re.split(r'[;,\s]+', value) if x.strip()))
    if not addresses or len(addresses) > 50 or any(
        not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', address) for address in addresses
    ):
        raise ValueError('Podaj poprawne adresy e-mail (maksymalnie 50), oddzielone przecinkiem.')
    return addresses


def parse_minimum(value):
    try:
        number = Decimal(str(value).replace(',', '.'))
        if not number.is_finite() or number < 0 or number > Decimal('99999999999.999'):
            raise ValueError
        if number != number.quantize(Decimal('.001')):
            raise ValueError
        return number
    except (InvalidOperation, ValueError):
        raise ValueError('Stan minimalny musi być nieujemną liczbą, do 3 miejsc po przecinku.') from None


_AVAILABLE_STOCK_PREDICATE = """
    stan_magazynowy > 0 AND COALESCE(is_blocked,0)=0
    AND TRIM(COALESCE(lokalizacja,'')) <> ''
    AND UPPER(TRIM(lokalizacja)) NOT IN ('LP01','MASZYNA','ZUŻYTE','ZUZYTE','ARCHIWUM')
    AND UPPER(TRIM(lokalizacja)) NOT LIKE 'OCZEK%'
"""

CATEGORY_ORDER = ('Surowce', 'Dodatki', 'Taśmy', 'Opakowania', 'Wyroby gotowe')


def _index_catalog(catalog_items):
    """Build stock and category lookup maps keyed by (stock_type, normalized_material)."""
    stocks = {}
    categories = {}
    for row in catalog_items:
        key = make_stock_key(row['stock_type'], row['material'])
        stocks[key] = Decimal(str(row['stock']))
        categories[key] = row['category']
    return stocks, categories


def catalog(cursor, strict=False):
    """Return unified available stock across raw materials, additives, packaging, tapes and finished goods."""
    items_by_key = {}

    def _merge(material_name, stock_val, stock_type, category, default_unit, is_tape=0):
        name = str(material_name or '').strip()
        if not name:
            return
        key = make_stock_key(stock_type, name)
        stock_dec = Decimal(str(stock_val or 0))
        existing = items_by_key.get(key)
        if existing:
            existing['stock'] = existing['stock'] + stock_dec
            if is_tape:
                existing['is_tape'] = 1
                existing['category'] = 'Taśmy'
                existing['default_unit'] = 'rolki'
        else:
            items_by_key[key] = {
                'material': name,
                'stock': stock_dec,
                'stock_type': stock_type,
                'category': category,
                'default_unit': default_unit,
                'is_tape': int(bool(is_tape)),
            }

    # 1. Surowce (active stock + dictionary items so 0-stock raw materials can also be monitored)
    try:
        cursor.execute(f"""
            SELECT nazwa AS material,
                   COALESCE(SUM(CASE WHEN {_AVAILABLE_STOCK_PREDICATE} THEN stan_magazynowy ELSE 0 END), 0) AS stock
            FROM magazyn_surowce
            WHERE nazwa IS NOT NULL AND TRIM(nazwa) <> ''
            GROUP BY nazwa
        """)
        for row in cursor.fetchall() or []:
            _merge(row['material'], row['stock'], STOCK_TYPE_RAW, 'Surowce', 'kg')
    except Exception as exc:
        if strict and getattr(exc, 'errno', None) != 1146:
            raise

    try:
        cursor.execute("SELECT DISTINCT nazwa FROM slownik_surowcow WHERE nazwa IS NOT NULL AND TRIM(nazwa) <> ''")
        for row in cursor.fetchall() or []:
            name = str(row['nazwa']).strip()
            if name and make_stock_key(STOCK_TYPE_RAW, name) not in items_by_key:
                _merge(name, Decimal(0), STOCK_TYPE_RAW, 'Surowce', 'kg')
    except Exception as exc:
        if strict and getattr(exc, 'errno', None) != 1146:
            raise

    # 2. Dodatki
    try:
        cursor.execute(f"""
            SELECT nazwa AS material,
                   COALESCE(SUM(CASE WHEN {_AVAILABLE_STOCK_PREDICATE} THEN stan_magazynowy ELSE 0 END), 0) AS stock
            FROM magazyn_dodatki
            WHERE nazwa IS NOT NULL AND TRIM(nazwa) <> ''
            GROUP BY nazwa
        """)
        for row in cursor.fetchall() or []:
            _merge(row['material'], row['stock'], STOCK_TYPE_ADDITIVE, 'Dodatki', 'kg')
    except Exception as exc:
        if strict and getattr(exc, 'errno', None) != 1146:
            raise

    # 3. Opakowania i taśmy (shared inventory across halls)
    try:
        cursor.execute(f"""
            SELECT nazwa AS material,
                   MAX(CASE WHEN UPPER(COALESCE(typ_opakowania,'')) LIKE 'TAŚM%'
                     OR UPPER(COALESCE(typ_opakowania,'')) LIKE 'TASM%'
                     OR UPPER(nazwa) LIKE '%TAŚM%' OR UPPER(nazwa) LIKE '%TASM%'
                     THEN 1 ELSE 0 END) AS is_tape,
                   COALESCE(SUM(CASE WHEN {_AVAILABLE_STOCK_PREDICATE} THEN stan_magazynowy ELSE 0 END), 0) AS stock
            FROM magazyn_opakowania
            WHERE nazwa IS NOT NULL AND TRIM(nazwa) <> ''
            GROUP BY nazwa
        """)
        for row in cursor.fetchall() or []:
            is_tape = bool(row.get('is_tape'))
            _merge(
                row['material'],
                row['stock'],
                STOCK_TYPE_PACKAGING,
                'Taśmy' if is_tape else 'Opakowania',
                'rolki' if is_tape else 'szt.',
                is_tape=1 if is_tape else 0,
            )
    except Exception as exc:
        if strict and getattr(exc, 'errno', None) != 1146:
            raise

    # 4. Wyroby gotowe (PSD + AGRO)
    for finished_table in ('magazyn_palety', 'magazyn_palety_agro'):
        try:
            cursor.execute(f"""
                SELECT produkt AS material,
                       COALESCE(SUM(CASE WHEN waga_netto > 0 AND COALESCE(is_blocked,0)=0
                         AND TRIM(COALESCE(lokalizacja,'')) <> ''
                         AND UPPER(TRIM(lokalizacja)) NOT IN ('ZUŻYTE','ZUZYTE','ARCHIWUM')
                         AND UPPER(TRIM(lokalizacja)) NOT LIKE 'OCZEK%'
                         THEN waga_netto ELSE 0 END), 0) AS stock
                FROM {finished_table}
                WHERE produkt IS NOT NULL AND TRIM(produkt) <> ''
                GROUP BY produkt
            """)
            for row in cursor.fetchall() or []:
                _merge(row['material'], row['stock'], STOCK_TYPE_FINISHED, 'Wyroby gotowe', 'kg')
        except Exception as exc:
            if strict and getattr(exc, 'errno', None) != 1146:
                raise

    order_map = {cat: idx for idx, cat in enumerate(CATEGORY_ORDER)}
    return sorted(
        items_by_key.values(),
        key=lambda item: (order_map.get(item['category'], 99), item['material'].casefold()),
    )


def build_alert_email(rule, stock, minimum):
    """Render a table-based email with inline styles for mail clients."""
    def quantity(value):
        number = format(Decimal(str(value)), ',.3f').rstrip('0').rstrip('.')
        return number.replace(',', ' ').replace('.', ',')

    category = rule.get('category') or stock_type_label(resolve_rule_stock_type(rule))
    environment = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parents[2] / 'templates'),
        autoescape=select_autoescape(['html']),
    )
    return environment.get_template('emails/packaging_stock_alert.html').render(
        material=str(rule['material']).strip(), unit=rule['unit'], group=rule.get('group_name', ''),
        category=category,
        stock=quantity(stock), minimum=quantity(minimum),
        shortage=quantity(max(Decimal(0), minimum - stock)),
        checked_at=datetime.now(ZoneInfo('Europe/Warsaw')).strftime('%d.%m.%Y · %H:%M'),
    )


def run_check():
    """One notification per shortage episode; a failed delivery retries after 30 minutes."""
    from app.core.instance_mode import is_test_instance
    from app.services.email_service import EmailService
    if is_test_instance():
        return
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    locked = False
    try:
        cursor.execute('SELECT GET_LOCK(%s,0) AS acquired', ('packaging_alerts_' + connection.database,))
        locked = cursor.fetchone()['acquired'] == 1
        if not locked:
            return
        cursor.execute("SHOW TABLES LIKE 'packaging_alert_rules'")
        if not cursor.fetchone():
            return  # Configuration has not been opened yet; no implicit migration in worker.
        stocks, categories = _index_catalog(catalog(cursor, strict=True))
        if not stocks:
            return
        try:
            cooldown_hours = max(1, int(os.getenv('STOCK_ALERT_MIN_COOLDOWN_HOURS', '6')))
        except (TypeError, ValueError):
            cooldown_hours = 6
        cursor.execute("""SELECT r.*, g.name AS group_name, g.recipients, g.cc_recipients,
            (r.next_attempt IS NULL OR r.next_attempt <= NOW()) AS retry_ready,
            (r.sent_at IS NOT NULL AND r.sent_at > DATE_SUB(NOW(), INTERVAL %s HOUR)) AS in_send_cooldown
            FROM packaging_alert_rules r JOIN packaging_alert_groups g ON g.id=r.group_id
            WHERE r.enabled=1""", (cooldown_hours,))
        for rule in cursor.fetchall():
            rule_stock_type = resolve_rule_stock_type(rule, stocks)
            key = make_stock_key(rule_stock_type, rule['material'])
            stock = stocks.get(key, Decimal(0))
            minimum = Decimal(str(rule['minimum']))
            if stock > minimum:
                cursor.execute("""UPDATE packaging_alert_rules SET notified=0, next_attempt=NULL,
                    last_error=NULL, checked_at=NOW() WHERE id=%s""", (rule['id'],))
            elif not rule['notified'] and rule['retry_ready'] and not rule.get('in_send_cooldown'):
                material_name = str(rule['material']).strip()
                category_label = categories.get(key) or stock_type_label(rule_stock_type)
                rule['category'] = category_label
                rule['group_name'] = 'Do: ' + rule['recipients'] + (' · DW: ' + rule['cc_recipients'] if rule.get('cc_recipients') else '')
                body = build_alert_email(rule, stock, minimum)
                success, message = EmailService().send_report_email(
                    parse_recipients(rule['recipients']),
                    f'Niski stan magazynowy ({category_label}): {material_name}', body,
                    cc_emails=parse_recipients(rule.get('cc_recipients') or '', optional=True),
                    log_connection=connection, log_source='Stany minimalne — automat')
                if success:
                    cursor.execute("""UPDATE packaging_alert_rules SET notified=1, sent_at=NOW(),
                        checked_at=NOW(), last_error=NULL, next_attempt=NULL WHERE id=%s""", (rule['id'],))
                else:
                    cursor.execute("""UPDATE packaging_alert_rules SET checked_at=NOW(), last_error=%s,
                        next_attempt=DATE_ADD(NOW(), INTERVAL 30 MINUTE) WHERE id=%s""", (message, rule['id']))
            else:
                cursor.execute('UPDATE packaging_alert_rules SET checked_at=NOW() WHERE id=%s', (rule['id'],))
            connection.commit()
    finally:
        try:
            if locked:
                cursor.execute('SELECT RELEASE_LOCK(%s)', ('packaging_alerts_' + connection.database,))
                cursor.fetchone()
        finally:
            cursor.close()
            connection.close()


def send_summary(connection, group_id):
    """Send all enabled shortages to the selected recipients, including notified ones."""
    from app.services.email_service import EmailService
    from app.core.instance_mode import is_test_instance
    if is_test_instance():
        return False, 'Wysyłanie e-maili jest wyłączone w izolowanej instancji testowej.'
    lock_name = 'packaging_alerts_' + connection.database
    cursor = connection.cursor(dictionary=True)
    locked = False
    try:
        cursor.execute('SELECT GET_LOCK(%s,0) AS acquired', (lock_name,))
        locked = cursor.fetchone()['acquired'] == 1
        if not locked:
            return False, 'Trwa sprawdzanie lub wysyłka powiadomień. Spróbuj ponownie za chwilę.'
        cursor.execute('SELECT * FROM packaging_alert_groups WHERE id=%s', (group_id,))
        group = cursor.fetchone()
        if not group:
            return False, 'Nie znaleziono adresów odbiorców.'
        stocks, categories = _index_catalog(catalog(cursor))
        cursor.execute('SELECT * FROM packaging_alert_rules WHERE enabled=1 ORDER BY material')
        rows = []
        order_map = {cat: idx for idx, cat in enumerate(CATEGORY_ORDER)}
        for rule in cursor.fetchall():
            rule_stock_type = resolve_rule_stock_type(rule, stocks)
            key = make_stock_key(rule_stock_type, rule['material'])
            stock = stocks.get(key, Decimal(0))
            minimum = Decimal(str(rule['minimum']))
            if stock <= minimum:
                category_label = categories.get(key) or stock_type_label(rule_stock_type)
                rows.append(dict(
                    rule,
                    material=str(rule['material']).strip(),
                    stock_type=rule_stock_type,
                    category=category_label,
                    stock=stock,
                    shortage=max(Decimal(0), minimum - stock),
                ))
        rows.sort(key=lambda row: (order_map.get(row['category'], 99), row['material'].casefold()))
        if not rows:
            from app.services.email_log_service import EmailLogService
            message = 'Brak pozycji na poziomie lub poniżej stanu minimalnego. Nie wysłano e-maila.'
            cursor.execute('SELECT smtp_username FROM uzytkownik_email_settings WHERE user_id=0')
            sender = cursor.fetchone() or {}
            EmailLogService.log_email_attempt(
                sender=sender.get('smtp_username') or 'Konto systemowe',
                recipients=parse_recipients(group['recipients']) + parse_recipients(group.get('cc_recipients') or '', optional=True),
                subject='Zestawienie niskich stanów magazynowych', source='Stany minimalne — ręcznie',
                success=False, status='SKIPPED', error_message=message, connection=connection)
            return False, message
        environment = Environment(
            loader=FileSystemLoader(Path(__file__).resolve().parents[2] / 'templates'),
            autoescape=select_autoescape(['html']),
        )
        environment.filters['stock_quantity'] = lambda value: format(Decimal(str(value)), ',.3f').rstrip('0').rstrip('.').replace(',', ' ').replace('.', ',')
        body = environment.get_template('emails/packaging_stock_summary.html').render(
            rows=rows, group='Do: ' + group['recipients'] + (' · DW: ' + group['cc_recipients'] if group.get('cc_recipients') else ''), material='Zestawienie niskich stanów magazynowych',
            checked_at=datetime.now(ZoneInfo('Europe/Warsaw')).strftime('%d.%m.%Y · %H:%M'),
        )
        success, message = EmailService().send_report_email(
            parse_recipients(group['recipients']),
            'Zestawienie niskich stanów magazynowych', body,
            cc_emails=parse_recipients(group.get('cc_recipients') or '', optional=True),
            log_connection=connection, log_source='Stany minimalne — ręcznie',
        )
        if success:
            for row in rows:
                # A manual copy to other recipients does not acknowledge their automatic alarm.
                if row.get('group_id') != group_id:
                    continue
                cursor.execute('''UPDATE packaging_alert_rules SET notified=1, sent_at=NOW(),
                    checked_at=NOW(), last_error=NULL, next_attempt=NULL WHERE id=%s''', (row['id'],))
            connection.commit()
            return True, f'Wysłano e-mail zbiorczy: {len(rows)} pozycji. Do: {group["recipients"]}.'
        return False, message
    finally:
        try:
            if locked:
                cursor.execute('SELECT RELEASE_LOCK(%s)', (lock_name,))
                cursor.fetchone()
        finally:
            cursor.close()
