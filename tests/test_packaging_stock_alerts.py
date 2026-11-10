from decimal import Decimal
from unittest.mock import patch
import pytest

from app.services.packaging_stock_alerts import parse_minimum, parse_recipients, run_check


@pytest.mark.parametrize('value', ['-1', 'NaN', 'Infinity', 'x', '0.0001', '100000000000'])
def test_invalid_minimum(value):
    with pytest.raises(ValueError):
        parse_minimum(value)


def test_comma_and_duplicate_addresses():
    assert parse_minimum('12,500') == Decimal('12.5')
    assert parse_recipients('A@firma.pl; a@firma.pl\nb@firma.pl') == ['a@firma.pl', 'b@firma.pl']
    with pytest.raises(ValueError):
        parse_recipients('invalid')


class MemoryCursor:
    def __init__(self):
        self.stock = 9
        self.rule = dict(id=1, material='Etykiety', minimum=10, unit='szt.',
                         recipients='zakupy@firma.pl', notified=0, retry_ready=1, group_id=1)
        self.result = []
        self.sql = []

    def execute(self, statement, params=()):
        self.sql.append(statement)
        if 'GET_LOCK' in statement:
            self.result = [dict(acquired=1)]
        elif 'RELEASE_LOCK' in statement or 'SHOW TABLES' in statement:
            self.result = [dict(found=1)]
        elif 'FROM magazyn_opakowania' in statement:
            self.result = [dict(material='Etykiety', stock=self.stock)]
        elif 'FROM packaging_alert_rules r' in statement:
            self.result = [self.rule.copy()]
        elif 'SET notified=0' in statement:
            self.rule['notified'] = 0
        elif 'SET notified=1' in statement:
            self.rule['notified'] = 1
        elif 'last_error=%s' in statement:
            self.rule['retry_ready'] = 0

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result

    def close(self):
        pass


class MemoryConnection:
    database = 'isolated_test'

    def __init__(self):
        self.query = MemoryCursor()

    def cursor(self, **kwargs):
        return self.query

    def commit(self):
        pass

    def close(self):
        pass


def test_one_alert_until_stock_recovers_then_rearms():
    connection = MemoryConnection()
    with patch('app.services.packaging_stock_alerts.get_db_connection', return_value=connection), \
         patch('app.core.instance_mode.is_test_instance', return_value=False), \
         patch('app.services.email_service.EmailService.send_report_email', return_value=(True, 'OK')) as send:
        run_check()
        run_check()
        assert send.call_count == 1
        connection.query.stock = 10  # Equality is safe and rearms.
        run_check()
        assert send.call_count == 1
        connection.query.stock = 0
        run_check()
        assert send.call_count == 2
    assert any('RELEASE_LOCK' in sql for sql in connection.query.sql)


def test_failed_send_is_not_marked_delivered_and_retry_is_delayed():
    connection = MemoryConnection()
    with patch('app.services.packaging_stock_alerts.get_db_connection', return_value=connection), \
         patch('app.core.instance_mode.is_test_instance', return_value=False), \
         patch('app.services.email_service.EmailService.send_report_email', return_value=(False, 'SMTP unavailable')) as send:
        run_check()
        run_check()
        assert send.call_count == 1
        assert connection.query.rule['notified'] == 0


def test_test_instance_never_connects_or_sends():
    with patch('app.core.instance_mode.is_test_instance', return_value=True), \
         patch('app.services.packaging_stock_alerts.get_db_connection') as connect:
        run_check()
        connect.assert_not_called()


@pytest.mark.parametrize('role,status', [('pracownik', 403), ('lider', 200), ('zarzad', 200), ('masteradmin', 200)])
def test_configuration_access(role, status):
    from flask import Flask, Blueprint
    from app.blueprints.admin.packaging_alerts import register_packaging_alert_routes
    application = Flask(__name__)
    application.secret_key = 'isolated-unit-test'
    blueprint = Blueprint('admin', __name__)
    register_packaging_alert_routes(blueprint)
    application.register_blueprint(blueprint)
    client = application.test_client()
    with client.session_transaction() as session:
        session.update(zalogowany=True, rola=role)
    connection = MemoryConnection()
    with patch('app.blueprints.admin.packaging_alerts.get_db_connection', return_value=connection) as connect, \
         patch('app.blueprints.admin.packaging_alerts.ensure_schema'), \
         patch('app.blueprints.admin.packaging_alerts.catalog', return_value=[]), \
         patch('app.blueprints.admin.packaging_alerts.render_template', return_value='configured'):
        assert client.get('/admin/ustawienia/stany-minimalne', headers={'Accept':'application/json'}).status_code == status
        if status == 403:
            connect.assert_not_called()


def test_email_formats_quantities_and_escapes_material_names():
    from app.services.packaging_stock_alerts import build_alert_email
    html = build_alert_email({'material':'Folia <script>alert(1)</script>', 'unit':'szt.', 'group_name':'Zakupy'}, Decimal('16'), Decimal('4000'))
    assert '<script>' not in html
    assert '&lt;script&gt;' in html
    assert '4 000' in html
    assert '3 984' in html
    assert '4000.000' not in html
    assert 'AGROMES' in html


def test_cc_header_and_smtp_envelope():
    from email import message_from_string
    from unittest.mock import MagicMock
    from app.services.email_service import EmailService
    smtp = MagicMock()
    smtp.sendmail.return_value = {}
    config = dict(configured=True, server='smtp.firma.pl',port=465,security='SSL',username='sender@firma.pl',password='fake',is_custom=False)
    with patch.object(EmailService,'get_smtp_config_for_user',return_value=config), patch(
        'app.services.email_service.smtp_target_allowed',return_value=(True,'')), patch(
        'app.services.email_service.secure_smtp_connection',return_value=smtp), patch(
        'app.services.email_log_service.EmailLogService.log_email_attempt'):
        success,_ = EmailService().send_report_email(['do@firma.pl'],'Test','<p>Test</p>',cc_emails=['dw@firma.pl','do@firma.pl'])
    assert success
    args = smtp.sendmail.call_args.args
    assert args[1] == ['do@firma.pl','dw@firma.pl']
    message = message_from_string(args[2])
    assert message['To'] == 'do@firma.pl'
    assert message['Cc'] == 'dw@firma.pl'


class SummaryCursor(MemoryCursor):
    def execute(self, statement, params=()):
        if 'FROM packaging_alert_groups WHERE id=' in statement:
            self.result = [dict(id=1,name='Zakupy',recipients='do@firma.pl',cc_recipients='dw@firma.pl')]
        elif 'FROM packaging_alert_rules WHERE enabled=1' in statement:
            self.sql.append(statement)
            self.result = [self.rule.copy()]
        else:
            super().execute(statement,params)


def test_manual_summary_sends_to_and_cc_and_suppresses_duplicate_automatic_alarm():
    from app.services.packaging_stock_alerts import send_summary
    connection = MemoryConnection()
    connection.query = SummaryCursor()
    connection.query.rule['notified'] = 1  # Explicit manual resend must be possible.
    with patch('app.core.instance_mode.is_test_instance',return_value=False), patch(
        'app.services.email_service.EmailService.send_report_email',return_value=(True,'OK')) as send:
        success,_ = send_summary(connection,1)
    assert success
    assert send.call_args.args[0] == ['do@firma.pl']
    assert send.call_args.kwargs['cc_emails'] == ['dw@firma.pl']
    assert 'Etykiety' in send.call_args.args[2]
    assert connection.query.rule['notified'] == 1


def test_manual_summary_does_not_send_when_stock_is_safe():
    from app.services.packaging_stock_alerts import send_summary
    connection = MemoryConnection()
    connection.query = SummaryCursor()
    connection.query.stock = 10
    with patch('app.core.instance_mode.is_test_instance',return_value=False), patch(
        'app.services.email_service.EmailService.send_report_email') as send, patch(
        'app.services.email_log_service.EmailLogService.log_email_attempt') as log:
        success,message = send_summary(connection,1)
    assert not success
    assert 'Brak opakowań' in message
    send.assert_not_called()

    assert log.call_args.kwargs['status'] == 'SKIPPED'
    assert log.call_args.kwargs['connection'] is connection


def test_bulk_rules_validate_each_selected_minimum():
    from werkzeug.datastructures import MultiDict
    from app.blueprints.admin.packaging_alerts import prepare_bulk_rules
    form = MultiDict([('selected','0'),('selected','1'),('material_0','Folia'),('minimum_0','100'),('unit_0','szt.'),('material_1','Kalka'),('minimum_1','25,5'),('unit_1','m')])
    rows = prepare_bulk_rules(form,[{'material':'Folia'},{'material':'Kalka'}])
    assert rows == [('Folia',Decimal('100'),'szt.'),('Kalka',Decimal('25.5'),'m')]
    form['minimum_1'] = ''
    with pytest.raises(ValueError,match='Kalka'):
        prepare_bulk_rules(form,[{'material':'Folia'},{'material':'Kalka'}])


def test_bulk_rules_ignore_unselected_and_reject_unknown_material():
    from werkzeug.datastructures import MultiDict
    from app.blueprints.admin.packaging_alerts import prepare_bulk_rules
    form = MultiDict([('selected','0'),('material_0','Folia'),('minimum_0','100'),('unit_0','szt.'),('material_1','Kalka'),('minimum_1','')])
    assert len(prepare_bulk_rules(form,[{'material':'Folia'},{'material':'Kalka'}])) == 1
    with pytest.raises(ValueError):
        prepare_bulk_rules(form,[])
    with pytest.raises(ValueError):
        prepare_bulk_rules(MultiDict(),[{'material':'Folia'}])


def test_saving_recipients_does_not_require_group_name():
    from flask import Flask, Blueprint
    from unittest.mock import MagicMock
    from app.blueprints.admin.packaging_alerts import register_packaging_alert_routes
    application = Flask(__name__)
    application.secret_key = 'isolated-unit-test'
    blueprint = Blueprint('admin', __name__)
    register_packaging_alert_routes(blueprint)
    blueprint.add_url_rule('/email', endpoint='email_center', view_func=lambda:'OK')
    application.register_blueprint(blueprint)
    client = application.test_client()
    with client.session_transaction() as session:
        session.update(zalogowany=True,rola='masteradmin')
    connection = MagicMock()
    with patch('app.blueprints.admin.packaging_alerts.get_db_connection',return_value=connection), patch(
        'app.blueprints.admin.packaging_alerts.ensure_schema'), patch(
        'app.blueprints.admin.packaging_alerts.catalog',return_value=[]):
        response = client.post('/admin/ustawienia/stany-minimalne',data={'action':'group','recipients':'do@firma.pl','cc_recipients':'dw@firma.pl'})
    assert response.status_code == 302
    sql, values = connection.cursor.return_value.execute.call_args.args
    assert 'INSERT INTO packaging_alert_groups' in sql
    assert values[1:] == ('do@firma.pl','dw@firma.pl')
    connection.commit.assert_called_once()


@pytest.mark.parametrize('code,expected',[(62,'nie pasuje'),(10,'ważność')])
def test_smtp_test_reports_certificate_failure_without_testing_password(code,expected):
    import ssl
    from app.services.email_service import EmailService
    error=ssl.SSLCertVerificationError('Certificate verification failed')
    error.verify_code=code
    with patch('app.services.email_service.smtp_target_allowed',return_value=(True,'')), patch(
        'app.services.email_service.secure_smtp_connection',side_effect=error):
        success,message=EmailService().test_connection('smtp.example.com',465,'SSL','user@example.com','fake')
    assert not success
    assert expected in message


def test_missing_smtp_configuration_is_recorded_before_transport():
    from app.services.email_service import EmailService
    with patch.object(EmailService,'get_smtp_config_for_user',return_value={'configured':False,'username':'sender@example.com'}), patch(
        'app.services.email_log_service.EmailLogService.log_email_attempt') as log, patch(
        'app.services.email_service.secure_smtp_connection') as connect:
        success,message=EmailService().send_report_email(['to@example.com'],'Test','<p>Test</p>')
    assert not success
    assert log.call_args.kwargs['success'] is False
    assert 'SMTP' in log.call_args.kwargs['error_message']
    connect.assert_not_called()


def test_email_log_reuses_supplied_connection():
    from unittest.mock import MagicMock
    from app.repositories.email_log_repository import EmailLogRepository
    connection=MagicMock()
    with patch('app.repositories.email_log_repository.get_db_connection') as connect:
        EmailLogRepository.create_log('sender@example.com','to@example.com','Test',connection=connection)
    connect.assert_not_called()
    connection.close.assert_not_called()
    connection.commit.assert_called_once()
    assert any('INSERT INTO email_logs' in call.args[0] for call in connection.cursor.return_value.execute.call_args_list)


def test_manual_summary_includes_shortages_assigned_to_other_recipients():
    from app.services.packaging_stock_alerts import send_summary
    connection=MemoryConnection()
    connection.query=SummaryCursor()
    connection.query.rule['group_id']=99
    with patch('app.core.instance_mode.is_test_instance',return_value=False), patch(
        'app.services.email_service.EmailService.send_report_email',return_value=(True,'OK')) as send:
        success,_=send_summary(connection,1)
    assert success
    assert 'Etykiety' in send.call_args.args[2]
    assert send.call_args.args[0]==['do@firma.pl']
    assert connection.query.rule['notified']==0
    queries=[sql for sql in connection.query.sql if 'FROM packaging_alert_rules' in sql]
    # The query selects all shortages; the chosen recipient set is only the destination.
    assert not any('group_id=' in sql for sql in queries)
