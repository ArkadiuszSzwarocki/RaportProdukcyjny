"""Write commands separating warehouse thresholds from e-mail notification routing."""
from app.services.packaging_stock_alerts import parse_recipients


def save_recipient_group(cursor, recipients_raw, cc_recipients_raw='', group_id=''):
    """Create or update a recipient group for stock shortage alerts."""
    recipients = ','.join(parse_recipients(recipients_raw))
    cc_recipients = ','.join(parse_recipients(cc_recipients_raw, optional=True))
    name = recipients[:100]
    if str(group_id or '').strip():
        cursor.execute(
            'UPDATE packaging_alert_groups SET name=%s, recipients=%s, cc_recipients=%s WHERE id=%s',
            (name, recipients, cc_recipients, int(group_id)),
        )
    else:
        cursor.execute(
            'INSERT INTO packaging_alert_groups(name,recipients,cc_recipients) VALUES (%s,%s,%s)',
            (name, recipients, cc_recipients),
        )


def delete_recipient_group(cursor, group_id):
    """Detach any alert rules assigned to a recipient group, disable their mail, and delete the group."""
    parsed_id = int(group_id)
    cursor.execute(
        'UPDATE packaging_alert_rules SET group_id=NULL, enabled=0 WHERE group_id=%s',
        (parsed_id,),
    )
    cursor.execute('DELETE FROM packaging_alert_groups WHERE id=%s', (parsed_id,))


def upsert_stock_threshold(cursor, material, stock_type, minimum, unit):
    """Save a warehouse minimum threshold without altering existing e-mail routing."""
    cursor.execute(
        """INSERT INTO packaging_alert_rules(material,stock_type,minimum,unit,group_id,enabled)
           VALUES (%s,%s,%s,%s,NULL,0)
           ON DUPLICATE KEY UPDATE material=VALUES(material), minimum=VALUES(minimum), unit=VALUES(unit)""",
        (material, stock_type, minimum, unit),
    )


def delete_stock_threshold(cursor, rule_id):
    """Delete a minimum-stock threshold rule by id."""
    cursor.execute('DELETE FROM packaging_alert_rules WHERE id=%s', (int(rule_id),))


def assign_rule_email_settings(cursor, rule_ids, group_id, enabled):
    """Assign recipient groups and enable/disable automatic e-mail notifications for selected rules."""
    valid_ids = list(dict.fromkeys(int(item) for item in (rule_ids or [])))
    if not valid_ids:
        raise ValueError('Zaznacz przynajmniej jedną pozycję.')

    raw_group = str(group_id or '').strip()
    parsed_group_id = int(raw_group) if raw_group else None
    if enabled and parsed_group_id is None:
        raise ValueError('Wybierz odbiorców e-mail przed włączeniem powiadomień.')

    if parsed_group_id is not None:
        cursor.execute('SELECT id FROM packaging_alert_groups WHERE id=%s', (parsed_group_id,))
        if not cursor.fetchone():
            raise ValueError('Wybierz poprawną grupę odbiorców e-mail.')

    enabled_flag = 1 if (enabled and parsed_group_id is not None) else 0
    for rule_id in valid_ids:
        cursor.execute(
            'UPDATE packaging_alert_rules SET group_id=%s, enabled=%s WHERE id=%s',
            (parsed_group_id, enabled_flag, rule_id),
        )


def toggle_rule_email_enabled(cursor, rule_id):
    """Toggle automatic e-mail notifications for a rule, requiring a recipient group before enabling."""
    parsed_id = int(rule_id)
    cursor.execute('SELECT id, group_id, enabled FROM packaging_alert_rules WHERE id=%s', (parsed_id,))
    row = cursor.fetchone()
    if not row:
        raise ValueError('Nie znaleziono wskazanej pozycji.')
    group_id = row['group_id'] if isinstance(row, dict) else row[1]
    currently_enabled = row['enabled'] if isinstance(row, dict) else row[2]
    if not currently_enabled and not group_id:
        raise ValueError('Najpierw przypisz odbiorców e-mail dla tej pozycji.')
    cursor.execute('UPDATE packaging_alert_rules SET enabled=1-enabled WHERE id=%s', (parsed_id,))
