# cspell:words fitz pixmap startdoc UZUPELNIENIA
"""No live printers or databases: verify correlation, uncertainty and replay safety."""
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from printer_server.office_config import office_printers
from printer_server import office_ipp as ipp
from printer_server import office_jobs as bridge


class ConfigurationTests(unittest.TestCase):
    def test_no_printer_enabled_by_default(self):
        with patch.dict(os.environ, {'OFFICE_PRINTERS_JSON':'{}'}):
            self.assertEqual(office_printers(),{})

    def test_disabled_monday_placeholder_is_not_a_target(self):
        with patch.dict(os.environ, {'OFFICE_PRINTERS_JSON':json.dumps({'brother':{'enabled':False,'ipp_uri':'DO_UZUPELNIENIA'}})}):
            self.assertEqual(office_printers(),{})

    def test_only_configured_private_printer_address_is_allowed(self):
        for uri in ('ipp://127.0.0.1/ipp/print','ipp://8.8.8.8/ipp/print','ipp://user:pass@192.168.1.20/ipp/print','file:///etc/passwd','ipp://192.168.1.20/ipp/print?x=1'):
            with self.subTest(uri=uri), patch.dict(os.environ, {'OFFICE_PRINTERS_JSON':json.dumps({'b':{'enabled':True,'windows_name':'Brother','ipp_uri':uri}})}):
                with self.assertRaises(ValueError): office_printers()

    def test_windows_queue_required_and_real_private_ipp_accepted(self):
        with patch.dict(os.environ, {'OFFICE_PRINTERS_JSON':json.dumps({'b':{'enabled':True,'windows_name':'Brother','ipp_uri':'ipp://192.168.1.20/ipp/print'}})}):
            self.assertEqual(office_printers()['b']['windows_name'],'Brother')
        with patch.dict(os.environ, {'OFFICE_PRINTERS_JSON':json.dumps({'b':{'enabled':True}})}):
            with self.assertRaises(ValueError): office_printers()


class ProtocolTests(unittest.TestCase):
    def test_windows_printed_or_complete_is_not_device_confirmation(self):
        for state in (0x80,0x1000):
            self.assertEqual(bridge.windows_status({'Status':state})[0],'SENT_TO_PRINTER')
        self.assertEqual(bridge.windows_status({'Status':0x20})[0],'ATTENTION')

    def test_only_exact_unique_ipp_name_can_confirm(self):
        with patch.object(ipp,'_jobs',return_value=[(2,{'job-name':['other'],'job-state':[9]})]):
            self.assertIsNone(ipp.device_job_status('unused','RP-unique'))
        with patch.object(ipp,'_jobs',return_value=[(2,{'job-name':['RP-unique'],'job-state':[9],'job-state-reasons':['job-completed-successfully']})]):
            self.assertEqual(ipp.device_job_status('unused','RP-unique')[0],'DEVICE_COMPLETED')

    def test_forwarded_completed_job_cannot_confirm_paper(self):
        with patch.object(ipp,'_jobs',return_value=[(2,{'job-name':['RP-unique'],'job-state':[9],'job-state-reasons':['queued-in-device']})]):
            self.assertEqual(ipp.device_job_status('unused','RP-unique')[0],'SENT_TO_PRINTER')

    def test_device_errors_and_warnings_are_distinct(self):
        for reason,state in [('job-completed-with-errors','FAILED'),('job-completed-with-warnings','DEVICE_WARNING')]:
            with self.subTest(reason=reason),patch.object(ipp,'_jobs',return_value=[(2,{'job-name':['RP-unique'],'job-state':[9],'job-state-reasons':[reason]})]):
                self.assertEqual(ipp.device_job_status('unused','RP-unique')[0],state)

    def test_ipp_decode_multivalue_and_reject_truncation(self):
        frame = struct.pack('>HHI',0x0101,0,1)+b'\x02'+ipp._attribute(0x42,'job-name','RP-1')+ipp._attribute(0x23,'job-state',9)+ipp._attribute(0x44,'job-state-reasons','none')+ipp._attribute(0x44,'','queued-in-device')+b'\x03'
        self.assertEqual(ipp.decode_groups(frame)[0][1]['job-state-reasons'],['none','queued-in-device'])
        for value in (b'',frame[:-2],struct.pack('>HHI',0x0101,0x0400,1)+b'\x03'):
            with self.subTest(value=value),self.assertRaises(ValueError):ipp.decode_groups(value)


class DurableJobTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.store = bridge.OfficeJobs(Path(self.folder.name)/'jobs.sqlite3')
        self.key = str(uuid4())
        self.config = patch.object(bridge,'office_printers',return_value={'b':dict(windows_name='Brother Test',label='Test',ipp_uri='')})
        self.config.start()
        self.executor = patch.object(bridge.EXECUTOR,'submit')
        self.queue = self.executor.start()

    def tearDown(self):
        self.executor.stop(); self.config.stop(); self.folder.cleanup()

    def submit(self):
        return self.store.submit(self.key,'b',b'%PDF-test')

    def test_duplicate_submission_is_not_printed_twice(self):
        self.submit(); self.submit()
        self.queue.assert_called_once()
        with self.assertRaises(ValueError):self.store.submit(self.key,'b',b'%PDF-different')
        self.assertEqual(self.store.get(self.key)['status'],'BRIDGE_QUEUED')

    def test_terminal_confirmation_is_not_overwritten_by_stale_poll(self):
        self.submit()
        self.store.update(self.key,'DEVICE_COMPLETED','Exact device confirmation',123)
        self.store.update(self.key,'UNKNOWN','Delayed missing status')
        self.assertEqual(self.store.get(self.key)['status'],'DEVICE_COMPLETED')

    def test_missing_printer_and_invalid_upload_not_queued(self):
        with self.assertRaises(ValueError):self.store.submit(self.key,'unknown',b'%PDF-test')
        with self.assertRaises(ValueError):self.store.submit(self.key,'b',b'not pdf')
        self.queue.assert_not_called()

    def test_restarted_bridge_never_resubmits_pending_jobs(self):
        self.submit()
        with patch.object(bridge,'INSTANCE','different-process'):
            self.assertEqual(self.store.refresh(self.key)['status'],'UNKNOWN')
        self.queue.assert_called_once()

    def test_missing_spool_job_stays_unconfirmed(self):
        self.submit(); self.store.update(self.key,'QUEUED','queued',123)
        fake = types.SimpleNamespace(OpenPrinter=MagicMock(side_effect=RuntimeError('Gone')))
        with patch.dict('sys.modules',{'win32print':fake}):
            self.assertEqual(self.store.refresh(self.key)['status'],'UNKNOWN')

    def test_reused_windows_job_id_does_not_confirm_other_document(self):
        self.submit(); self.store.update(self.key,'QUEUED','queued',123)
        fake = types.SimpleNamespace(OpenPrinter=MagicMock(return_value=1),ClosePrinter=MagicMock(),GetJob=MagicMock(return_value={'pDocument':'other-report','Status':0x80}))
        with patch.dict('sys.modules',{'win32print':fake}):
            self.assertEqual(self.store.refresh(self.key)['status'],'UNKNOWN')

    def test_started_then_failed_is_uncertain_and_pdf_is_removed(self):
        self.submit(); path=Path(self.folder.name)/(self.key+'.pdf')
        def render(_path,_printer,_name,started):
            started(321)
            raise RuntimeError('Disconnected after submission')
        with patch.object(bridge,'render_windows_pdf',side_effect=render):self.store._print(self.key,path)
        self.assertEqual(self.store.get(self.key)['status'],'UNKNOWN')
        self.assertEqual(self.store.get(self.key)['spool_id'],321)
        self.assertFalse(path.exists())
        self.queue.assert_called_once()


class RendererTests(unittest.TestCase):
    def test_startdoc_job_id_is_saved_and_gdi_failure_aborts(self):
        for drawn,expected_abort in [(2,False),(0,True)]:
            with self.subTest(drawn=drawn):
                dc=MagicMock();dc.StartDoc.return_value=123;dc.GetDeviceCaps.return_value=100
                page=MagicMock();page.get_pixmap.return_value=types.SimpleNamespace(samples=b'\xff'*12,width=2,height=2)
                pdf=MagicMock();pdf.needs_pass=False;pdf.__len__.return_value=1;pdf.__iter__.return_value=iter([page])
                fitz=types.SimpleNamespace(open=MagicMock(return_value=pdf),csRGB=1)
                win=types.SimpleNamespace(CreateDC=MagicMock(return_value=dc))
                stretch=MagicMock(return_value=drawn)
                started=MagicMock()
                with patch.dict('sys.modules',{'pymupdf':fitz,'win32ui':win}),patch('ctypes.windll',types.SimpleNamespace(gdi32=types.SimpleNamespace(StretchDIBits=stretch)),create=True):
                    if expected_abort:
                        with self.assertRaises(RuntimeError):bridge.render_windows_pdf('fake.pdf','Brother','RP-1',started)
                    else:bridge.render_windows_pdf('fake.pdf','Brother','RP-1',started)
                started.assert_called_once_with(123)
                self.assertEqual(dc.AbortDoc.called,expected_abort)
                dc.DeleteDC.assert_called_once();pdf.close.assert_called_once()


class BridgeRoutesTests(unittest.TestCase):
    def test_new_routes_require_existing_bridge_token(self):
        from printer_server import server
        with patch.dict(os.environ,{'PRINTER_BRIDGE_TOKEN':'secret'}),patch.dict(server.app.config,{'TESTING':False}),patch.object(server,'_office_jobs') as jobs:
            client=server.app.test_client()
            self.assertEqual(client.get('/office-jobs/'+str(uuid4())).status_code,401)
            self.assertEqual(client.post('/office-jobs').status_code,401)
            jobs.assert_not_called()

    def test_status_route_is_read_only_and_returns_no_queue_credentials(self):
        from printer_server import server
        key=uuid4();store=MagicMock();store.refresh.return_value=dict(request_id=str(key),printer_key='b',status='UNKNOWN',note='No proof',spool_id=None,updated_at=1,printer_json='secret')
        with patch.dict(server.app.config,{'TESTING':True}),patch.object(server,'_office_jobs',return_value=store):
            response=server.app.test_client().get('/office-jobs/'+str(key))
        self.assertEqual(response.status_code,200)
        self.assertNotIn('printer_json',response.json['job'])
        store.submit.assert_not_called()



class ApplicationTests(unittest.TestCase):
    def setUp(self):
        from flask import Flask
        from app.blueprints.magazyn_dostawy.base import magazyn_dostawy_bp
        # Import route definitions before registering this blueprint.
        from app.blueprints.magazyn_dostawy.routes import document_monitoring
        self.routes = document_monitoring
        self.app = Flask(__name__)
        self.app.secret_key = 'tests-only'
        self.app.register_blueprint(magazyn_dostawy_bp)
        self.client = self.app.test_client()

    def login(self, name='test', role='pracownik'):
        with self.client.session_transaction() as session:
            session.update(zalogowany=True, login=name, rola=role)

    def test_options_need_login_and_do_not_contact_bridge(self):
        self.assertEqual(self.client.get('/magazyn-dostawy/api/tracked-print/options',headers={'Accept':'application/json'}).status_code,401)
        self.login()
        with patch.dict(os.environ,{'OFFICE_PRINTERS_JSON':'{}','OFFICE_PRINTERS_FILE':''}),patch('app.services.tracked_movement_print._bridge') as network:
            response=self.client.get('/magazyn-dostawy/api/tracked-print/options')
        self.assertEqual(response.json,{'success':True,'printers':[]})
        network.assert_not_called()

    def test_status_only_owner_or_management_can_read(self):
        from app.repositories.movement_print_job_repository import MovementPrintJobRepository as Jobs
        from app.services import tracked_movement_print as service
        self.login()
        key=uuid4()
        row=dict(request_id=str(key),user_login='someone-else',status='UNKNOWN',note='No proof',printer_label='Brother',spool_id=None)
        with patch.object(Jobs,'get',return_value=row),patch.object(service,'refresh',return_value=row) as refresh:
            response=self.client.get('/magazyn-dostawy/api/tracked-print/'+str(key))
            self.assertEqual(response.status_code,403);refresh.assert_not_called()
            self.login(role='lider')
            self.assertEqual(self.client.get('/magazyn-dostawy/api/tracked-print/'+str(key)).status_code,200)

    def test_client_cannot_supply_arbitrary_render_url(self):
        from app.services import tracked_movement_print as service
        self.login()
        key=str(uuid4())
        with patch.object(self.routes,'_tracked_print_documents',return_value=[('delivery','doc-1','MM-1')]),patch.object(service,'submit',return_value=dict(request_id=key,status='PREPARING',note='Prepare',printer_label='Brother',spool_id=None)) as submit:
            response=self.client.post('/magazyn-dostawy/api/tracked-print',json=dict(event_id=key,documents=[dict(kind='delivery',id='doc-1')],printer_key='brother',url='http://evil.invalid/'))
        self.assertEqual(response.status_code,202)
        self.assertNotIn('evil',str(submit.call_args))

    def test_newer_browser_click_does_not_inherit_old_confirmation(self):
        from app.repositories.movement_print_job_repository import MovementPrintJobRepository as Jobs
        self.login(role='lider')
        document=dict(document_kind='delivery',document_id='d',last_print_event_id='new-browser-event',last_click=None)
        job=dict(request_id='old-tracked-event',status='DEVICE_COMPLETED')
        with patch.object(self.routes.MovementDocumentRepository,'monitor',return_value=([document],[])),patch.object(Jobs,'latest_for_documents',return_value={('delivery','d'):job}),patch.object(self.routes,'render_template',return_value='OK'):
            self.assertEqual(self.client.get('/magazyn-dostawy/historia-druku').status_code,200)
        self.assertIsNone(document['tracked_print'])

    def test_unconfigured_printer_does_not_create_job(self):
        from app.services import tracked_movement_print as service
        with self.app.test_request_context(),patch.object(service,'office_printers',return_value={}),patch.object(service.Jobs,'create') as create:
            with self.assertRaises(ValueError):service.submit(self.app,str(uuid4()),'missing','test',[('delivery','doc','MM')])
        create.assert_not_called()

    def test_duplicate_app_request_never_starts_second_worker(self):
        from app.services import tracked_movement_print as service
        row=dict(status='QUEUED')
        with self.app.test_request_context(),patch.object(service,'office_printers',return_value={'b':{'label':'Brother'}}),patch.object(service.Jobs,'create',return_value=(False,row)),patch.object(service.EXECUTOR,'submit') as schedule,patch.object(service,'url_for',return_value='/canonical/report'):
            self.assertEqual(service.submit(self.app,str(uuid4()),'b','test',[('delivery','doc','MM')]),row)
        schedule.assert_not_called()

    def test_lost_post_response_is_unknown_not_retried(self):
        from app.services import tracked_movement_print as service
        key=str(uuid4())
        with patch.object(service,'_render_reports'),patch.object(service,'_bridge',side_effect=TimeoutError('Lost response')) as network,patch.object(service.Jobs,'update') as update,patch.object(service.SLOTS,'release'):
            service._work(self.app,key,'b',['/report'])
        network.assert_called_once()
        self.assertEqual(update.call_args.args[1],'UNKNOWN')


if __name__ == '__main__':unittest.main()

