from pathlib import Path
from jinja2 import Environment,ChoiceLoader,DictLoader,FileSystemLoader


def render(summary):
    root=Path(__file__).resolve().parents[1]
    environment=Environment(loader=ChoiceLoader([DictLoader({'layout.html':'{% block extra_css %}{% endblock %}{% block content %}{% endblock %}{% block footer_scripts %}{% endblock %}'}),FileSystemLoader(str(root/'templates'))]))
    return environment.get_template('warehouse_v2/summary.html').render(summary=summary,linia='ALL',static_version='test',url_for=lambda endpoint,**kwargs:'/static/'+kwargs['filename'] if endpoint=='static' else '/warehouse-v2/')


def test_summary_uses_local_qr_encoder_and_unclipped_native_details():
    html=render({'Test':dict(type='Surowiec',unit='kg',total=150,count=1,pallets=[dict(id=1,displayId='SUR123',location='MS01',amount=150,unit='kg',is_first_fifo=True,nr_partii='LOT',data_produkcji='2026-10-01',data_przydatnosci='2027-10-01')])})
    assert 'api.qrserver.com' not in html
    assert '/static/js/qrcode.min.js' in html
    assert 'data-qr="SUR123"' in html
    assert 'data-qr-value="SUR123"' in html
    assert '<details class="warehouse-product-card"' in html
    assert 'max-height: 1000px' not in html
    assert 'summaryQrDialog' in html
    assert '1. do zużycia' in html


def test_summary_renders_empty_inventory_without_broken_qr_images():
    html=render({})
    assert 'Brak stanów magazynowych' in html
    assert 'data-qr=' not in html
