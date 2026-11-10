# cspell:words TINYINT
"""Persistent, database-scoped packaging shortage notifications."""
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
        minimum DECIMAL(14,3) NOT NULL, unit VARCHAR(20) NOT NULL,
        group_id INT NOT NULL, enabled TINYINT NOT NULL DEFAULT 0,
        notified TINYINT NOT NULL DEFAULT 0, sent_at DATETIME NULL,
        checked_at DATETIME NULL, next_attempt DATETIME NULL, last_error TEXT NULL,
        UNIQUE KEY material_unique (material),
        FOREIGN KEY (group_id) REFERENCES packaging_alert_groups(id))
        ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


def ensure_schema(connection):
    cursor = connection.cursor()
    try:
        for statement in SCHEMA:
            cursor.execute(statement)
        cursor.execute("SHOW COLUMNS FROM packaging_alert_groups LIKE 'cc_recipients'")
        if not cursor.fetchone():
            cursor.execute('ALTER TABLE packaging_alert_groups ADD COLUMN cc_recipients TEXT NULL')
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


def catalog(cursor):
    # Shared inventory: never restrict packaging to a production hall.
    cursor.execute("""SELECT nazwa AS material,
        MAX(CASE WHEN UPPER(COALESCE(typ_opakowania,'')) LIKE 'TAŚM%'
          OR UPPER(COALESCE(typ_opakowania,'')) LIKE 'TASM%'
          OR UPPER(nazwa) LIKE '%TAŚM%' OR UPPER(nazwa) LIKE '%TASM%'
          THEN 1 ELSE 0 END) AS is_tape,
        COALESCE(SUM(CASE WHEN stan_magazynowy > 0 AND COALESCE(is_blocked,0)=0
          AND TRIM(COALESCE(lokalizacja,'')) <> ''
          AND UPPER(TRIM(lokalizacja)) NOT IN ('LP01','MASZYNA','ZUŻYTE','ZUZYTE','ARCHIWUM')
          AND UPPER(TRIM(lokalizacja)) NOT LIKE 'OCZEK%'
          THEN stan_magazynowy ELSE 0 END),0) AS stock
        FROM magazyn_opakowania GROUP BY nazwa ORDER BY nazwa""")
    return cursor.fetchall()


def build_alert_email(rule, stock, minimum):
    """Render a table-based email with inline styles for mail clients."""
    def quantity(value):
        number = format(Decimal(str(value)), ',.3f').rstrip('0').rstrip('.')
        return number.replace(',', ' ').replace('.', ',')

    environment = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parents[2] / 'templates'),
        autoescape=select_autoescape(['html']),
    )
    return environment.get_template('emails/packaging_stock_alert.html').render(
        material=rule['material'], unit=rule['unit'], group=rule.get('group_name', ''),
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
        stocks = {row['material']: Decimal(str(row['stock'])) for row in catalog(cursor)}
        cursor.execute("""SELECT r.*, g.name AS group_name, g.recipients, g.cc_recipients,
            (r.next_attempt IS NULL OR r.next_attempt <= NOW()) AS retry_ready
            FROM packaging_alert_rules r JOIN packaging_alert_groups g ON g.id=r.group_id
            WHERE r.enabled=1""")
        for rule in cursor.fetchall():
            stock = stocks.get(rule['material'], Decimal(0))
            minimum = Decimal(str(rule['minimum']))
            if stock >= minimum:
                cursor.execute("""UPDATE packaging_alert_rules SET notified=0, next_attempt=NULL,
                    last_error=NULL, checked_at=NOW() WHERE id=%s""", (rule['id'],))
            elif not rule['notified'] and rule['retry_ready']:
                rule['group_name'] = 'Do: ' + rule['recipients'] + (' · DW: ' + rule['cc_recipients'] if rule.get('cc_recipients') else '')
                body = build_alert_email(rule, stock, minimum)
                success, message = EmailService().send_report_email(
                    parse_recipients(rule['recipients']),
                    'Niski stan opakowań: ' + rule['material'], body,
                    cc_emails=parse_recipients(rule.get('cc_recipients') or '', optional=True),
                    log_connection=connection, log_source='Niskie stany — automat')
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
        stocks = {row['material']: Decimal(str(row['stock'])) for row in catalog(cursor)}
        cursor.execute('SELECT * FROM packaging_alert_rules WHERE enabled=1 ORDER BY material')
        rows = []
        for rule in cursor.fetchall():
            stock = stocks.get(rule['material'], Decimal(0))
            minimum = Decimal(str(rule['minimum']))
            if stock < minimum:
                rows.append(dict(rule, stock=stock, shortage=minimum-stock))
        if not rows:
            from app.services.email_log_service import EmailLogService
            message = 'Brak opakowań poniżej minimum we wszystkich aktywnych regułach. Nie wysłano e-maila.'
            cursor.execute('SELECT smtp_username FROM uzytkownik_email_settings WHERE user_id=0')
            sender = cursor.fetchone() or {}
            EmailLogService.log_email_attempt(
                sender=sender.get('smtp_username') or 'Konto systemowe',
                recipients=parse_recipients(group['recipients']) + parse_recipients(group.get('cc_recipients') or '', optional=True),
                subject='Zestawienie niskich stanów opakowań', source='Niskie stany — ręcznie',
                success=False, status='SKIPPED', error_message=message, connection=connection)
            return False, message
        environment = Environment(
            loader=FileSystemLoader(Path(__file__).resolve().parents[2] / 'templates'),
            autoescape=select_autoescape(['html']),
        )
        environment.filters['stock_quantity'] = lambda value: format(Decimal(str(value)), ',.3f').rstrip('0').rstrip('.').replace(',', ' ').replace('.', ',')
        body = environment.get_template('emails/packaging_stock_summary.html').render(
            rows=rows, group='Do: ' + group['recipients'] + (' · DW: ' + group['cc_recipients'] if group.get('cc_recipients') else ''), material='Zestawienie niskich stanów',
            checked_at=datetime.now(ZoneInfo('Europe/Warsaw')).strftime('%d.%m.%Y · %H:%M'),
        )
        success, message = EmailService().send_report_email(
            parse_recipients(group['recipients']),
            'Zestawienie niskich stanów opakowań', body,
            cc_emails=parse_recipients(group.get('cc_recipients') or '', optional=True),
            log_connection=connection, log_source='Niskie stany — ręcznie',
        )
        if success:
            for row in rows:
                # A manual copy to other recipients does not acknowledge their automatic alarm.
                if row.get('group_id') != group_id:
                    continue
                cursor.execute('''UPDATE packaging_alert_rules SET notified=1, sent_at=NOW(),
                    checked_at=NOW(), last_error=NULL, next_attempt=NULL WHERE id=%s''', (row['id'],))
            connection.commit()
            return True, f'Wysłano e-mail zbiorczy: {len(rows)} opakowań. Do: {group["recipients"]}.'
        return False, message
    finally:
        try:
            if locked:
                cursor.execute('SELECT RELEASE_LOCK(%s)', (lock_name,))
                cursor.fetchone()
        finally:
            cursor.close()
