# cspell:words pytestmark
"""Create, read, edit and delete notes against the isolated CI database."""
import uuid
from datetime import date
from flask import Flask
import pytest
from app.db import get_db_connection
from app.blueprints.shifts.base import shifts_bp
from app.services.dashboard_service import DashboardService

pytestmark=pytest.mark.require_db


@pytest.mark.parametrize('line',['PSD','AGRO'])
def test_shift_note_lifecycle_persists_to_shared_table(line):
    marker='TEST-NOTE-'+uuid.uuid4().hex
    app=Flask(__name__)
    app.secret_key='isolated-note-db-test'
    app.register_blueprint(shifts_bp)
    client=app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True,login=marker,rola='lider')
    try:
        response=client.post('/add_shift_note',json={'note':marker,'date':'2040-01-02','linia':line})
        assert response.status_code==200 and response.json['success'],response.json
        note_id=response.json['id']
        notes=DashboardService.get_shift_notes(date(2040,1,2),linia=line)
        assert any(n['id']==note_id and n['note']==marker for n in notes)
        other='PSD' if line=='AGRO' else 'AGRO'
        assert not any(n['id']==note_id for n in DashboardService.get_shift_notes(date(2040,1,2),linia=other))
        response=client.post(f'/api/shift_note/{note_id}/update',json={'note':marker+' edited','linia':line})
        assert response.status_code==200 and response.json['success']
        assert any(n['id']==note_id and n['note']==marker+' edited' for n in DashboardService.get_shift_notes(date(2040,1,2),linia=line))
        response=client.post(f'/api/shift_note/{note_id}/delete',json={'linia':line})
        assert response.status_code==200 and response.json['success']
        assert not any(n['id']==note_id for n in DashboardService.get_shift_notes(date(2040,1,2),linia=line))
    finally:
        conn=get_db_connection()
        try:
            cursor=conn.cursor()
            cursor.execute('DELETE FROM shift_notes WHERE author=%s',(marker,))
            conn.commit()
        finally:
            conn.close()
