"""Roll withdrawals remain distinct, transactional and idle until explicitly installed."""
import json
from unittest.mock import MagicMock, patch
import pytest
from app.services.folio_assignment_service import FolioAssignmentService
from app.services.folio_service import FolioService


def assignment_connection(status='w toku', slots=None, stock=2307):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.lastrowid = 999
    cursor.fetchone.side_effect = [
        {'id':322,'produkt':'Milk','data_planu':'2026-10-25','status':status,'opakowanie_id':1},
        {'id':1,'nazwa':'Film','stan_magazynowy':stock,'nr_palety':'SOURCE-SSCC','is_blocked':False},
        None, {'nazwa':'Film'}]
    cursor.fetchall.return_value = slots or []
    return conn,cursor


@pytest.mark.parametrize('state,role,slots,expected_counter', [
    ('w toku','active',[],120),
    ('w toku','auto',[{'id':9,'licznik_start':100}],None),
    ('zaplanowane','auto',[],None),
    ('zawieszone','prepared',[],None)])
def test_withdrawal_creates_separate_roll_and_only_once_decrements_source(state,role,slots,expected_counter):
    conn,cur = assignment_connection(state,slots)
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn), patch('app.services.folio_service._get_mqtt_counter',return_value=120), patch('app.utils.pallet_id.generate_pallet_id',return_value='ROLL-SSCC'):
        success,message = FolioAssignmentService.assign(1,322,700,'operator',role)
    assert success, message
    updates=[call.args for call in cur.execute.call_args_list if call.args[0].startswith('UPDATE magazyn_opakowania')]
    assert len(updates)==1 and updates[0][1]==(1607.0,1)
    link=[call.args for call in cur.execute.call_args_list if call.args[0].startswith('INSERT INTO agro_plan_opakowania')][0]
    assert link[1]==(322,999,700.0,expected_counter)
    assert not any('SET stan_poczatkowy = stan_poczatkowy +' in call.args[0] for call in cur.execute.call_args_list)
    movements=[call.args[1] for call in cur.execute.call_args_list if call.args[0].startswith('INSERT INTO magazyn_ruch')]
    assert json.loads(movements[1][-1])['source_sscc']=='SOURCE-SSCC'
    conn.commit.assert_called_once()


@pytest.mark.parametrize('amount', [None,0,-1,701.5,'nan','inf'])
def test_invalid_amount_never_connects(amount):
    with patch('app.services.folio_assignment_service.get_db_connection') as connect:
        assert not FolioAssignmentService.assign(1,322,amount,'operator')[0]
    connect.assert_not_called()


def test_third_roll_rejected_before_stock_changes():
    conn,cur=assignment_connection(slots=[{'id':1,'licznik_start':100},{'id':2,'licznik_start':None}])
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn):
        assert not FolioAssignmentService.assign(1,322,700,'operator')[0]
    assert all(call.args[0].startswith('SELECT') for call in cur.execute.call_args_list)
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_insufficient_stock_rejected():
    conn,cur=assignment_connection(stock=600)
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn):
        assert not FolioAssignmentService.assign(1,322,700,'operator')[0]
    assert all(call.args[0].startswith('SELECT') for call in cur.execute.call_args_list)


def test_failure_after_stock_update_rolls_back_everything():
    conn,cur=assignment_connection()
    def execute(sql,args):
        if sql.startswith('INSERT INTO agro_plan_opakowania'):
            raise RuntimeError('simulated storage failure')
    cur.execute.side_effect=execute
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn), patch('app.utils.pallet_id.generate_pallet_id',return_value='ROLL-SSCC'):
        assert not FolioAssignmentService.assign(1,322,700,'operator')[0]
    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()


def test_prepared_roll_never_consumes_machine_counter():
    conn=MagicMock(); cur=conn.cursor.return_value
    cur.fetchall.return_value=[{'link_id':9,'plan_id':322,'opakowanie_id':99,'stan_poczatkowy':700,'licznik_start':None,'source_metadata':'{"source_sscc":"SOURCE"}'}]
    with patch('app.services.folio_service._get_mqtt_counter',return_value=99999):
        roll=FolioService.get_active_rolls(322,external_conn=conn)[0]
    assert roll['is_prepared'] and roll['live_zuzyte']==0 and roll['szacowane_pozostalo']==700
    assert roll['source_sscc']=='SOURCE'


@pytest.mark.parametrize('close_ok',[True,False])
def test_roll_swap_uses_one_transaction_and_no_stock_withdrawal(close_ok):
    conn=MagicMock(); cur=conn.cursor.return_value
    cur.fetchone.side_effect=[{'plan_id':322},{'status':'w toku'}]
    cur.fetchall.return_value=[{'id':9,'licznik_start':100},{'id':10,'licznik_start':None}]
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn), patch.object(FolioService,'close_roll',return_value=(close_ok,'closure failed')) as close, patch.object(FolioService,'print_closed_roll_labels') as printer, patch('app.services.folio_service._get_mqtt_counter',return_value=500):
        success,message=FolioAssignmentService.activate(10,'operator',9,100)
    assert success is close_ok
    assert close.call_args.kwargs['external_conn'] is conn
    if close_ok:
        conn.commit.assert_called_once(); printer.assert_called_once()
        assert any(call.args[1]==(500,10) for call in cur.execute.call_args_list)
    else:
        conn.rollback.assert_called_once(); conn.commit.assert_not_called(); printer.assert_not_called()
    assert not any('UPDATE magazyn_opakowania' in call.args[0] for call in cur.execute.call_args_list)


def test_retry_request_is_idempotent():
    conn=MagicMock(); cur=conn.cursor.return_value
    cur.fetchone.side_effect=[{'status':'w toku'}, {'id':99}]
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn):
        assert FolioAssignmentService.assign(1,322,700,'operator',request_key='da3c59b8-bcde-4afb-a540-4abbda0389c4')[0]
    assert all(call.args[0].startswith('SELECT') for call in cur.execute.call_args_list)
    conn.commit.assert_not_called()


@pytest.mark.parametrize('state,slots', [('zaplanowane', []), ('w toku', [{'id':9,'licznik_start':100}])])
def test_cannot_install_second_used_roll_or_install_on_planned_order(state, slots):
    conn,cur=assignment_connection(state,slots)
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn):
        assert not FolioAssignmentService.assign(1,322,700,'operator','active')[0]
    assert all(call.args[0].startswith('SELECT') for call in cur.execute.call_args_list)


def test_incompatible_film_rejected_without_withdrawal():
    conn,cur=assignment_connection()
    cur.fetchone.side_effect=[{'id':322,'produkt':'Milk','data_planu':'2026-10-25','status':'w toku','opakowanie_id':1},
        {'id':1,'nazwa':'Wrong film','stan_magazynowy':2307,'nr_palety':'SOURCE'},None,{'nazwa':'Required film'}]
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn):
        assert not FolioAssignmentService.assign(1,322,700,'operator')[0]
    assert all(call.args[0].startswith('SELECT') for call in cur.execute.call_args_list)


def test_unused_prepared_roll_closes_without_consumption_or_loss():
    conn=MagicMock(); cur=conn.cursor.return_value
    cur.fetchone.side_effect=[{'plan_id':322,'opakowanie_id':999,'stan_poczatkowy':700,'licznik_start':None,'opak_nazwa':'Film'},
        {'data_planu':'2026-10-25','produkt':'Milk'},None,None,{'nr_palety':'ROLL-SSCC'}]
    with patch('app.services.folio_service.get_db_connection',return_value=conn), patch('app.services.folio_service._get_mqtt_counter',return_value=99999), patch('app.utils.pallet_id.is_valid_pallet_id',return_value=True), patch.object(FolioService,'print_closed_roll_labels'):
        assert FolioService.close_roll(9,700,'operator')[0]
    history=[call.args[1] for call in cur.execute.call_args_list if 'INSERT INTO agro_workowanie_rozliczenie' in call.args[0]][0]
    assert history[6]==0 and history[8]==0 and history[9]==700


def test_prepared_roll_cannot_be_marked_consumed_before_installation():
    conn=MagicMock(); cur=conn.cursor.return_value
    cur.fetchone.return_value={'plan_id':322,'opakowanie_id':999,'stan_poczatkowy':700,'licznik_start':None,'opak_nazwa':'Film'}
    with patch('app.services.folio_service.get_db_connection',return_value=conn):
        assert not FolioService.close_roll(9,0,'operator')[0]
    assert all(call.args[0].lstrip().startswith('SELECT') for call in cur.execute.call_args_list)



def test_plan_picker_only_returns_orders_with_selected_film_assigned():
    conn=MagicMock(); cur=conn.cursor.return_value
    cur.fetchone.return_value={'nazwa':'  Milk   Złoty '}
    cur.fetchall.return_value=[
        {'id':1,'wymagana_folia':'Milk Złoty','data_planu':'2026-10-25'},
        {'id':2,'wymagana_folia':'Milk Niebieski','data_planu':'2026-10-25'},
        {'id':3,'wymagana_folia':None,'data_planu':'2026-10-25'},
        {'id':4,'wymagana_folia':'milk złoty','data_planu':'2026-10-25'}]
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn):
        assert [row['id'] for row in FolioAssignmentService.plans(100)]==[1,4]
    assert cur.execute.call_args_list[0].args[1]==(100,)


@pytest.mark.parametrize('close_ok',[True,False])
def test_new_roll_replacement_closes_previous_within_same_transaction(close_ok):
    conn,cur=assignment_connection(slots=[{'id':9,'licznik_start':100},{'id':10,'licznik_start':None}])
    events=[]
    conn.commit.side_effect=lambda:events.append('commit')
    def close(link_id,remaining,user,**kwargs):
        assert link_id==9 and remaining==100 and kwargs['external_conn'] is conn
        kwargs['label_jobs'].append(({},None,None))
        return close_ok, 'closure failed'
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn), patch.object(FolioService,'close_roll',side_effect=close), patch.object(FolioService,'print_closed_roll_labels',side_effect=lambda jobs:events.append('print')), patch('app.services.folio_service._get_mqtt_counter',return_value=120), patch('app.utils.pallet_id.generate_pallet_id',return_value='NEW-ROLL'):
        success,message=FolioAssignmentService.assign(1,322,700,'operator',role='replace',previous_remaining=100)
    assert success is close_ok
    if close_ok:
        assert events==['commit','print']
        links=[call.args[1] for call in cur.execute.call_args_list if call.args[0].startswith('INSERT INTO agro_plan_opakowania')]
        assert links==[(322,999,700.0,120)]
    else:
        assert events==[]
        conn.rollback.assert_called_once()
        assert all(call.args[0].startswith('SELECT') for call in cur.execute.call_args_list)


@pytest.mark.parametrize('remaining',[None,'',-1,'nan','inf',0.5])
def test_replacement_requires_valid_previous_roll_remaining(remaining):
    conn,cur=assignment_connection(slots=[{'id':9,'licznik_start':100}])
    with patch('app.services.folio_assignment_service.get_db_connection',return_value=conn):
        assert not FolioAssignmentService.assign(1,322,700,'operator',role='replace',previous_remaining=remaining)[0]
    conn.commit.assert_not_called()
    assert all(call.args[0].startswith('SELECT') for call in cur.execute.call_args_list)
