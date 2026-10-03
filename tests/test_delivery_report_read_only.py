"""Opening a report cannot complete unresolved delivery items."""
import json
from unittest.mock import MagicMock

from flask import Flask
from app.blueprints.magazyn_dostawy.routes import transfer as module


def test_report_keeps_pending_document_even_if_pallet_is_on_rack(monkeypatch):
    conn = MagicMock()
    cursor = conn.cursor.return_value
    cursor.fetchone.return_value = {
        'id': 'doc', 'linia': 'AGRO', 'status': 'OCZEKUJE', 'supplier': 'Supplier',
        'items': json.dumps([{'id': 'one', 'nr_palety': 'P1', 'productName': 'Material', 'netWeight': 100}])}
    cursor.fetchall.side_effect = lambda: (
        [{'nr_palety': 'P1', 'lokalizacja': 'R010101', 'updated_at': None}]
        if 'SELECT nr_palety, lokalizacja' in cursor.execute.call_args.args[0] else [])
    monkeypatch.setattr(module, 'get_db_connection', lambda: conn)
    monkeypatch.setattr(module, 'render_template', lambda template, **context: context)
    with Flask(__name__).test_request_context('/magazyn-dostawy/raport-przesuniecia/doc'):
        context = module.raport_przesuniecia('doc')
    assert context['dostawa']['status'] == 'OCZEKUJE'
    assert context['pending_count'] == 1
    conn.commit.assert_not_called()
    assert all(not call.args[0].lstrip().startswith('UPDATE') for call in cursor.execute.call_args_list)
