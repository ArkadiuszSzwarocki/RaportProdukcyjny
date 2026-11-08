"""Read-only view of effective mail routing, without SMTP secrets."""
from app.db import get_db_connection
from app.services.email_service import EmailService
from app.services.auto_report.auto_report_recipients_service import AutoReportRecipientsService


def load_mail_routing():
    system = EmailService().get_smtp_config_for_user(None)
    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)
    try:
        cursor.execute('''SELECT s.user_id,u.login,s.smtp_username,s.smtp_server,s.is_active,
            s.domyslni_odbiorcy FROM uzytkownik_email_settings s
            LEFT JOIN uzytkownicy u ON u.id=s.user_id WHERE s.user_id<>0 ORDER BY u.login''')
        accounts = cursor.fetchall()
        cursor.execute('''SELECT smtp_username,odbiorcy,is_active,auto_send_on_dispatch,
            daily_report_enabled,daily_report_time FROM osip_email_settings WHERE id=1''')
        warehouse = cursor.fetchone() or {}
        cursor.execute("SHOW TABLES LIKE 'packaging_alert_groups'")
        groups = []
        if cursor.fetchone():
            cursor.execute('''SELECT g.id,g.recipients,g.cc_recipients,
                COUNT(r.id) AS rule_count,COALESCE(SUM(r.enabled=1),0) AS active_count
                FROM packaging_alert_groups g LEFT JOIN packaging_alert_rules r ON r.group_id=g.id
                GROUP BY g.id,g.recipients,g.cc_recipients ORDER BY g.id''')
            groups = cursor.fetchall()
    finally:
        cursor.close()
        connection.close()
    return dict(system={key:system.get(key) for key in ('username','server','sender_name','configured')},
                accounts=accounts,warehouse=warehouse,groups=groups,
                production_recipients=AutoReportRecipientsService.get_default_recipients('AGRO'))
