from unittest.mock import MagicMock, patch


def test_overview_exposes_effective_sender_without_secrets():
    from app.services.mail_routing_overview import load_mail_routing
    connection = MagicMock()
    cursor = connection.cursor.return_value
    cursor.fetchall.side_effect = [
        [dict(user_id=7,login='lider',smtp_username='personal@example.com')],
        [dict(id=1,recipients='to@example.com',cc_recipients='',rule_count=2,active_count=2)],
    ]
    cursor.fetchone.side_effect = [dict(smtp_username='legacy@example.com'), dict(found=1)]
    with patch('app.services.mail_routing_overview.get_db_connection',return_value=connection), patch(
        'app.services.mail_routing_overview.EmailService.get_smtp_config_for_user',return_value=dict(
            username='system@example.com',server='smtp.example.com',configured=True,password='SECRET-MUST-NOT-LEAK')), \
        patch('app.services.mail_routing_overview.AutoReportRecipientsService.get_default_recipients',return_value=['recipient@example.com']):
        view=load_mail_routing()
    assert view['system']['username']=='system@example.com'
    assert view['warehouse']['smtp_username']=='legacy@example.com'
    assert 'SECRET-MUST-NOT-LEAK' not in str(view)
    assert 'password' not in view['system']
    connection.commit.assert_not_called()
    assert all('smtp_password' not in call.args[0] for call in cursor.execute.call_args_list)


def test_report_links_and_account_editor_exist(app):
    from flask import url_for
    with app.test_request_context('/'):
        assert '/konto/7' in url_for('admin.email_account_edit',target_user_id=7)
        assert url_for('main.raport_podglad_pdf',data='2026-11-03',linia='AGRO')
        assert url_for('main.raport_zakoncz_zmiane_page',data='2026-11-03',linia='AGRO')
        assert url_for('magazyn_dostawy.print_daily_report_center',data='2026-11-03')
