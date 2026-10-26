from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from flask import Blueprint, Flask
from jinja2 import DictLoader, Environment
from app.blueprints.production.orders import register_production_order_routes


def test_workowanie_input_summary_appears_only_after_first_scan():
    source=(Path(__file__).parents[1]/'templates/dashboard/_dashboard_agro_settlement.html').read_text(encoding='utf-8')
    fragment=source[source.index('            {% set bb_set ='):source.index('            <!-- Sekcja: Analiza strat')]
    env=Environment(); env.globals['url_for']=lambda *args,**kwargs:'/scanner'
    render=env.from_string(fragment).render
    empty=render(wrctx={'bigbag_settlement':{'items':[]},'active_plan':{'id':322}})
    assert 'badge-bb-in' not in empty
    populated=render(wrctx={'bigbag_settlement':{'items':[{'id':1,'nr_palety':'SSCC','waga_kg':1000}]},'active_plan':{'id':322}})
    assert 'SSCC' in populated and 'badge-bb-in' in populated
    assert 'bb-scan-input' not in source and 'removeScannedBigBag' not in source


@pytest.mark.parametrize('allowed,selected,status',[(True,None,200),(True,322,200),(True,999,404),(False,None,403)])
def test_dedicated_scanner_uses_existing_workowanie_access_and_reads_only(allowed,selected,status):
    app=Flask(__name__); app.secret_key='bigbag-page-test'
    app.jinja_loader=DictLoader({'agro/bigbag_scanner.html':'Scanner {{ selected.id if selected else "choose" }}'})
    bp=Blueprint('production',__name__); register_production_order_routes(bp,lambda:'/'); app.register_blueprint(bp)
    client=app.test_client()
    with client.session_transaction() as state: state.update(zalogowany=True,rola='pracownik')
    conn=MagicMock(); conn.cursor.return_value.fetchall.return_value=[{'id':322,'produkt':'Milk','status':'w toku','data_planu':'2026-10-25'}]
    with patch('app.core.production_permissions._page_allowed',return_value=allowed), patch('app.blueprints.production.orders.get_db_connection',return_value=conn), patch('app.services.agro_workowanie_bigbag_service.AgroWorkowanieBigBagService.get_plan_bigbag_settlement',return_value={'items':[]}):
        response=client.get('/agro/wsad-bigbag'+('?plan_id='+str(selected) if selected else ''))
    assert response.status_code==status
    if status==200: assert '322' in response.text
    conn.commit.assert_not_called()
