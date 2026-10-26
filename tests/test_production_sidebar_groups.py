from pathlib import Path
from types import SimpleNamespace
from jinja2 import Environment,FileSystemLoader

ROOT=Path(__file__).resolve().parents[1]


def render(name, permissions=None, role='masteradmin', endpoint='main.index'):
    environment=Environment(loader=FileSystemLoader(str(ROOT/'templates')))
    return environment.get_template('includes/sidebar/'+name).render(
        effective_hall='AGRO',role=role,role_has_access=lambda key:True if permissions is None else key in permissions,
        request=SimpleNamespace(args={'linia':'AGRO'},path='/agro/lp01' if endpoint=='agro_warehouse.lp01_view' else '/',endpoint=endpoint,blueprint='agro_warehouse'),
        app=SimpleNamespace(view_functions={}),url_for=lambda endpoint,**kwargs:'/'+endpoint)


def test_material_links_are_in_a_nested_production_group_not_warehouse():
    html=render('_sidebar_agro.html',endpoint='agro_warehouse.lp01_view')
    assert '<details class="nav-sub-group" open>' in html
    assert 'Opakowania i LP01' in html
    assert 'Stanowisko LP01' in html and 'Opakowania Agro' in html
    warehouse=render('_sidebar_warehouse.html')
    assert 'agro_warehouse.lp01_view' not in warehouse
    assert 'agro_warehouse.opakowania' not in warehouse
    assert 'Rozliczenie MOM' not in warehouse
    assert 'Traceability' not in warehouse


def test_operator_retains_lp01_without_receiving_packaging_admin_access():
    html=render('_sidebar_agro.html',permissions={'agro.workowanie'},role='pracownik')
    assert 'Stanowisko LP01' in html
    assert 'agro_warehouse.opakowania' not in html


def test_mom_and_traceability_have_their_own_section():
    html=render('_sidebar_settlements.html')
    assert 'ROZLICZENIA I PARTIE' in html
    assert 'Rozliczenie MOM' in html
    assert 'Traceability (Śledzenie partii)' in html
    html=render('_sidebar_settlements.html',permissions=set(),role='laborant')
    assert 'Rozliczenie MOM' not in html and 'Traceability' not in html
