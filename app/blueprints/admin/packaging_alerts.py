"""Administration of monitored packaging and recipient groups."""
from flask import flash, redirect, render_template, request, url_for
from app.decorators import login_required, roles_required
from app.db import get_db_connection
from app.services.packaging_stock_alerts import catalog, ensure_schema, parse_minimum, parse_recipients, send_summary


def prepare_bulk_rules(form, materials):
    selected = list(dict.fromkeys(form.getlist('selected')))
    if not selected:
        raise ValueError('Zaznacz przynajmniej jeden materiał.')
    known = {row['material'] for row in materials}
    rows = []
    seen = set()
    for index in selected:
        if not index.isdigit():
            raise ValueError('Nieprawidłowy wybór materiału.')
        material = form.get('material_' + index, '')
        if material not in known or material in seen:
            raise ValueError('Lista materiałów zmieniła się. Otwórz okno ponownie.')
        seen.add(material)
        try:
            minimum = parse_minimum(form.get('minimum_' + index, ''))
        except ValueError as error:
            raise ValueError(f'{material}: {error}') from None
        unit = form.get('unit_' + index, '')
        if unit not in ('szt.', 'kg', 'm', 'rolki'):
            raise ValueError(f'{material}: wybierz jednostkę magazynową.')
        rows.append((material, minimum, unit))
    return rows


def register_packaging_alert_routes(bp):
    @bp.route('/admin/ustawienia/stany-minimalne', methods=['GET', 'POST'])
    @login_required
    @roles_required(['admin', 'masteradmin', 'zarzad', 'lider'])
    def packaging_alerts():
        connection = get_db_connection()
        cursor = None
        try:
            ensure_schema(connection)
            cursor = connection.cursor(dictionary=True)
            materials = catalog(cursor)
            for item in materials:
                item['category'] = 'Taśmy' if item.get('is_tape') else 'Pozostałe materiały'
            materials.sort(key=lambda item: (item['category'] != 'Taśmy', item['material'].casefold()))
            if request.method == 'POST':
                try:
                    action = request.form.get('action')
                    if action == 'summary':
                        success, message = send_summary(connection, int(request.form.get('group_id', '0')))
                        flash(message, 'success' if success else 'error')
                        return redirect(url_for('admin.email_center', tab='stany'))
                    if action == 'group':
                        recipients = ','.join(parse_recipients(request.form.get('recipients', '')))
                        cc_recipients = ','.join(parse_recipients(request.form.get('cc_recipients', ''), optional=True))
                        name = recipients[:100]
                        group_id = request.form.get('group_id', '')
                        if group_id:
                            cursor.execute('UPDATE packaging_alert_groups SET name=%s, recipients=%s, cc_recipients=%s WHERE id=%s',
                                           (name, recipients, cc_recipients, int(group_id)))
                        else:
                            cursor.execute('INSERT INTO packaging_alert_groups(name,recipients,cc_recipients) VALUES (%s,%s,%s)', (name, recipients, cc_recipients))
                    elif action == 'bulk_rules':
                        rows = prepare_bulk_rules(request.form, materials)
                        group_id = int(request.form.get('group_id', '0'))
                        cursor.execute('SELECT id FROM packaging_alert_groups WHERE id=%s', (group_id,))
                        if not cursor.fetchone():
                            raise ValueError('Wybierz adresy odbiorców dla zaznaczonych materiałów.')
                        connection.commit()
                        connection.start_transaction()
                        for material, minimum, unit in rows:
                            cursor.execute("""INSERT INTO packaging_alert_rules(material,minimum,unit,group_id,enabled)
                                VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE minimum=VALUES(minimum),
                                unit=VALUES(unit), group_id=VALUES(group_id), enabled=VALUES(enabled)""",
                                (material, minimum, unit, group_id, int(request.form.get('enabled') == 'on')))
                    elif action == 'rule':
                        material = request.form.get('material', '')
                        if material not in {row['material'] for row in materials}:
                            raise ValueError('Wybierz opakowanie z magazynu.')
                        minimum = parse_minimum(request.form.get('minimum', ''))
                        unit = request.form.get('unit', '')
                        if unit not in ('szt.', 'kg', 'm', 'rolki'):
                            raise ValueError('Wybierz jednostkę zgodną z ewidencją magazynową.')
                        group_id = int(request.form.get('group_id', '0'))
                        cursor.execute('SELECT id FROM packaging_alert_groups WHERE id=%s', (group_id,))
                        if not cursor.fetchone():
                            raise ValueError('Najpierw zapisz adresy odbiorców Do i DW.')
                        cursor.execute("""INSERT INTO packaging_alert_rules(material,minimum,unit,group_id,enabled)
                            VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE minimum=VALUES(minimum),
                            unit=VALUES(unit), group_id=VALUES(group_id), enabled=VALUES(enabled)""",
                            (material, minimum, unit, group_id, int(request.form.get('enabled') == 'on')))
                    elif action == 'toggle':
                        cursor.execute('UPDATE packaging_alert_rules SET enabled=1-enabled WHERE id=%s',
                                       (int(request.form.get('id', '0')),))
                    else:
                        raise ValueError('Nieznana operacja.')
                    connection.commit()
                    flash('Zapisano ustawienia stanów minimalnych.', 'success')
                except (ValueError, TypeError) as error:
                    connection.rollback()
                    flash(str(error), 'error')
                return redirect(url_for('admin.email_center', tab='stany'))
            cursor.execute('SELECT * FROM packaging_alert_groups ORDER BY recipients')
            groups = cursor.fetchall()
            cursor.execute('''SELECT r.*,g.recipients AS group_name,g.cc_recipients FROM packaging_alert_rules r
                JOIN packaging_alert_groups g ON g.id=r.group_id ORDER BY r.material''')
            rules = cursor.fetchall()
            stocks = {row['material']: row['stock'] for row in materials}
            for rule in rules:
                rule['stock'] = stocks.get(rule['material'], 0)
                rule['category'] = next((item['category'] for item in materials if item['material'] == rule['material']), 'Pozostałe materiały')
            rules.sort(key=lambda rule: (rule['category'] != 'Taśmy', rule['material'].casefold()))
            return render_template('admin/packaging_alerts.html', groups=groups, rules=rules, materials=materials, rules_by_material={rule['material']: rule for rule in rules})
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()
