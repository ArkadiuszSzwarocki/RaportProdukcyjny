"""Email Center routes for minimum-stock alert notifications and recipients."""
from flask import flash, redirect, render_template, request, url_for
from app.decorators import login_required, roles_required
from app.db import get_db_connection
from app.services.packaging_stock_alerts import CATEGORY_ORDER, catalog, ensure_schema, send_summary
from app.services.stock_alert_commands import (
    assign_rule_email_settings,
    delete_recipient_group,
    save_recipient_group,
    toggle_rule_email_enabled,
)
from app.services.stock_alert_queries import enrich_materials_and_rules, fetch_recipient_groups, fetch_rules


def register_stock_alert_email_routes(bp):
    """Register Email Center routes for stock-shortage e-mail routing and alerts."""
    @bp.route('/admin/ustawienia/poczta/alerty-stany', methods=['GET', 'POST'])
    @login_required
    @roles_required(['admin', 'masteradmin', 'zarzad', 'lider'])
    def stock_alert_emails():
        connection = get_db_connection()
        cursor = None
        try:
            ensure_schema(connection)
            cursor = connection.cursor(dictionary=True)
            if request.method == 'POST':
                try:
                    action = request.form.get('action')
                    if action == 'summary':
                        success, message = send_summary(connection, int(request.form.get('group_id', '0')))
                        flash(message, 'success' if success else 'error')
                        return redirect(url_for('admin.email_center', tab='stany'))
                    if action == 'group':
                        save_recipient_group(
                            cursor,
                            request.form.get('recipients', ''),
                            request.form.get('cc_recipients', ''),
                            request.form.get('group_id', ''),
                        )
                    elif action == 'delete_group':
                        delete_recipient_group(cursor, request.form.get('group_id', '0'))
                    elif action == 'assign_emails':
                        assign_rule_email_settings(
                            cursor,
                            request.form.getlist('rule_ids'),
                            request.form.get('group_id', ''),
                            request.form.get('enabled') == 'on',
                        )
                    elif action == 'toggle':
                        toggle_rule_email_enabled(cursor, request.form.get('id', '0'))
                    else:
                        raise ValueError('Nieznana operacja.')
                    connection.commit()
                    flash('Zapisano ustawienia powiadomień e-mail.', 'success')
                except (ValueError, TypeError) as error:
                    connection.rollback()
                    flash(str(error), 'error')
                return redirect(url_for('admin.email_center', tab='stany'))

            groups = fetch_recipient_groups(cursor)
            materials = catalog(cursor)
            rules = fetch_rules(cursor)
            _, rules, _ = enrich_materials_and_rules(materials, rules)
            active_email_count = sum(1 for rule in rules if rule.get('enabled') and rule.get('group_id'))
            unassigned_count = sum(1 for rule in rules if not rule.get('group_id'))
            return render_template(
                'admin/stock_alert_emails.html',
                groups=groups,
                rules=rules,
                categories=list(CATEGORY_ORDER),
                active_email_count=active_email_count,
                unassigned_count=unassigned_count,
            )
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()
