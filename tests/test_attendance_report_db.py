"""Exercise real MySQL row locking and roster lookup in an isolated database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
import threading
import uuid
import pytest
from flask import Flask
from app.db import get_db_connection
from app.services.attendance_write_service import lock_employee, insert_attendance_once
from app.services.leave_request_service import LeaveRequestService
from scripts.reports.attendance_data import load_daily_absences

pytestmark = pytest.mark.require_db
DAY = date(2040,1,16)


@pytest.fixture
def employee():
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO pracownicy(imie_nazwisko,widoczny_agro,urlop_biezacy,urlop_zalegly) VALUES (%s,0,0,0)",
                   ('TEST-ABSENCE-'+uuid.uuid4().hex,))
    pid = cursor.lastrowid; conn.commit(); conn.close()
    try:
        yield pid
    finally:
        conn = get_db_connection(); cursor = conn.cursor()
        for table in ('obecnosc','wnioski_wolne','obsada_zmiany'):
            cursor.execute(f'DELETE FROM {table} WHERE pracownik_id=%s', (pid,))
        cursor.execute('DELETE FROM pracownicy WHERE id=%s',(pid,))
        conn.commit(); conn.close()


def test_concurrent_identical_assignments_insert_only_once(employee):
    barrier = threading.Barrier(3)
    def save(_):
        conn = get_db_connection(); cursor = conn.cursor()
        try:
            barrier.wait(timeout=20)
            lock_employee(cursor, employee)
            added = insert_attendance_once(cursor, DAY, employee, 'L4', 8, 'Test')
            conn.commit()
            return added
        finally:
            conn.close()
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert sorted(pool.map(save, range(3))) == [False,False,True]
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM obecnosc WHERE pracownik_id=%s',(employee,))
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_concurrent_approvals_increment_balance_once(employee):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO wnioski_wolne(pracownik_id,typ,data_od,data_do) VALUES (%s,'Urlop',%s,%s)",
                   (employee,DAY,DAY))
    rid = cursor.lastrowid; conn.commit(); conn.close()
    barrier = threading.Barrier(3)
    def approve(_):
        with Flask(__name__).app_context():
            barrier.wait(timeout=20)
            return LeaveRequestService.approve_leave_request(rid, employee)[0]
    with ThreadPoolExecutor(max_workers=3) as pool:
        assert all(pool.map(approve, range(3)))
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute('SELECT urlop_biezacy FROM pracownicy WHERE id=%s',(employee,))
    assert cursor.fetchone()[0] == 1
    cursor.execute('SELECT COUNT(*) FROM obecnosc WHERE pracownik_id=%s',(employee,))
    assert cursor.fetchone()[0] == 1
    conn.close()


def test_l4_uses_last_assignment_before_absence_and_never_future_assignment(employee):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("INSERT INTO obsada_zmiany(data_wpisu,pracownik_id,sekcja,linia) VALUES ('2040-01-06',%s,'Zasyp','AGRO')",(employee,))
    cursor.execute("INSERT INTO obsada_zmiany(data_wpisu,pracownik_id,sekcja,linia) VALUES ('2040-01-17',%s,'Zasyp','PSD')",(employee,))
    cursor.execute("INSERT INTO obecnosc(data_wpisu,pracownik_id,typ,ilosc_godzin) VALUES (%s,%s,'L4',8)",(DAY,employee))
    conn.commit()
    cursor.execute('SELECT imie_nazwisko FROM pracownicy WHERE id=%s',(employee,))
    name = cursor.fetchone()[0]
    assert any(row['pracownik']==name and row['typ']=='L4' for row in load_daily_absences(conn,DAY,'AGRO'))
    assert not any(row['pracownik']==name for row in load_daily_absences(conn,DAY,'PSD'))
    conn.close()
