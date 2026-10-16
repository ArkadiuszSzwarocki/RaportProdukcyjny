"""A shared note table must remain reachable through the identifier allowlist."""
from datetime import date, datetime
from unittest.mock import MagicMock
from flask import Flask
import pytest
from app.blueprints.shifts import base as routes
from app.services.dashboard_service import DashboardService


@pytest.mark.parametrize('line',['PSD','AGRO'])
def test_note_creation_and_dashboard_read_use_existing_shared_storage(monkeypatch,line):
    app=Flask(__name__)
    app.secret_key='isolated-note-test'
    app.register_blueprint(routes.shifts_bp)
    connection=MagicMock()
    cursor=connection.cursor.return_value
    monkeypatch.setattr(routes,'get_db_connection',lambda:connection)
    client=app.test_client()
    with client.session_transaction() as state:
        state.update(zalogowany=True,login='test-leader',rola='lider')
    response=client.post('/add_shift_note',json={'note':'Saved note','date':'2040-01-02','linia':line})
    assert response.status_code==200 and response.json['success']
    inserts=[call.args for call in cursor.execute.call_args_list if call.args[0].startswith('INSERT')]
    assert len(inserts)==1 and 'INSERT INTO shift_notes ' in inserts[0][0]
    assert inserts[0][1][2]=='Saved note' and inserts[0][1][-1]==line
    connection.commit.assert_called_once()
    cursor.fetchall.return_value=[(response.json['id'],None,'Saved note','test-leader',date(2040,1,2),datetime(2040,1,2,8),line)]
    notes=DashboardService.get_shift_notes(date(2040,1,2),linia=line,cursor=cursor)
    assert notes[0]['note']=='Saved note' and notes[0]['linia']==line
    assert cursor.execute.call_args.args[1][-2:]==(line,line)
