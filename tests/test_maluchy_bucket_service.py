import pytest
from app.core.factory import create_app
from app.db import get_db_connection
from app.services.bucket_maluch_service import BucketMaluchService
from app.repositories.bucket_maluch_repository import BucketMaluchRepository


@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    return app


@pytest.fixture
def test_plan_with_szarza():
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    
    # 1. Create active Zasyp plan
    cur.execute(
        """
        INSERT INTO plan_produkcji (produkt, data_planu, sekcja, status, tonaz, tonaz_rzeczywisty, is_deleted)
        VALUES ('Test Produkt Maluchy', CURDATE(), 'Zasyp', 'w toku', 5000, 1000, 0)
        """
    )
    plan_id = cur.lastrowid
    
    # 2. Create a szarża
    cur.execute(
        """
        INSERT INTO szarze (plan_id, nr_szarzy, waga, data_dodania)
        VALUES (%s, 1, 1000, NOW())
        """,
        (plan_id,)
    )
    szarza_id = cur.lastrowid
    conn.commit()
    conn.close()

    yield plan_id, szarza_id

    # Cleanup
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM wiaderka_maluchy WHERE plan_id = %s", (plan_id,))
    cur.execute("DELETE FROM szarze WHERE plan_id = %s", (plan_id,))
    cur.execute("DELETE FROM plan_produkcji WHERE id = %s", (plan_id,))
    conn.commit()
    conn.close()


def test_bucket_lifecycle(test_plan_with_szarza):
    plan_id, szarza_id = test_plan_with_szarza

    # 1. Start bucket 04 (e.g. scanned as '4' or '04' or 'W04')
    success, msg, bucket = BucketMaluchService.start_bucket(
        kod_wiadra="04",
        plan_id=plan_id,
        linia="PSD",
        operator_login="operator_test"
    )
    assert success is True
    assert bucket is not None
    assert bucket['kod_wiadra'] == "04"
    assert bucket['status'] == "w_trakcie_nawazania"
    bucket_id = bucket['id']

    # 2. Add items from KO01 and KO40
    ok1, msg1, b1 = BucketMaluchService.add_item_to_bucket(
        bucket_id=bucket_id,
        stacja_kod="KO01",
        surowiec_nazwa="Premiks Witaminowy A",
        operator_login="operator_test"
    )
    assert ok1 is True
    assert len(b1['pozycje']) == 1

    ok2, msg2, b2 = BucketMaluchService.add_item_to_bucket(
        bucket_id=bucket_id,
        stacja_kod="KO40",
        surowiec_nazwa="Premiks Mineralny B",
        operator_login="operator_test"
    )
    assert ok2 is True
    assert len(b2['pozycje']) == 2

    # 3. Complete bucket
    ok_comp, msg_comp, b_comp = BucketMaluchService.complete_bucket(bucket_id, "operator_test")
    assert ok_comp is True
    assert b_comp['status'] == "skompletowane"

    # 4. Try scanning invalid mixer code (e.g. MI02, RACK-01) - MUST FAIL
    ok_bad, msg_bad, _ = BucketMaluchService.scan_and_dump_to_mixer(
        kod_wiadra="04",
        plan_id=plan_id,
        szarza_id=szarza_id,
        mieszalnik_kod="MI02",
        operator_login="operator_zasyp",
        linia="PSD"
    )
    assert ok_bad is False
    assert "MI01" in msg_bad

    # 5. Scan and dump to valid mixer MI01
    ok_dump, msg_dump, b_dump = BucketMaluchService.scan_and_dump_to_mixer(
        kod_wiadra="04",
        plan_id=plan_id,
        szarza_id=szarza_id,
        mieszalnik_kod="MI01",
        operator_login="operator_zasyp",
        linia="PSD"
    )
    assert ok_dump is True
    assert b_dump['status'] == "wrzucone_do_mieszalnika"
    assert b_dump['szarza_id'] == szarza_id
    assert b_dump['mieszalnik_kod'] == "MI01"


def test_maluchy_api(app, test_plan_with_szarza):
    plan_id, szarza_id = test_plan_with_szarza
    client = app.test_client()

    with client.session_transaction() as sess:
        sess['user_id'] = 1
        sess['rola'] = 'operator'
        sess['zalogowany'] = True
        sess['username'] = 'operator'

    # Start bucket via API (scanned as '08')
    resp = client.post('/maluchy/api/start', json={
        'kod_wiadra': '08',
        'plan_id': plan_id,
        'linia': 'PSD'
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['success'] is True
    assert data['bucket']['kod_wiadra'] == '08'
    bucket_id = data['bucket']['id']

    # Add item via API (KO35)
    resp_item = client.post('/maluchy/api/item/add', json={
        'bucket_id': bucket_id,
        'stacja_kod': 'KO35',
        'surowiec_nazwa': 'Sól mikro'
    })
    assert resp_item.status_code == 200
    assert len(resp_item.get_json()['bucket']['pozycje']) == 1

    # Complete bucket via API
    resp_comp = client.post('/maluchy/api/complete', json={'bucket_id': bucket_id})
    assert resp_comp.status_code == 200
    assert resp_comp.get_json()['bucket']['status'] == 'skompletowane'

    # Dump bucket to mixer MI01 via API
    resp_dump = client.post('/maluchy/api/dump-to-mixer', json={
        'kod_wiadra': '08',
        'plan_id': plan_id,
        'szarza_id': szarza_id,
        'mieszalnik_kod': 'MI01',
        'linia': 'PSD'
    })
    assert resp_dump.status_code == 200
    assert resp_dump.get_json()['bucket']['status'] == 'wrzucone_do_mieszalnika'
    assert resp_dump.get_json()['bucket']['mieszalnik_kod'] == 'MI01'

    # Test rejecting 2nd bucket into same szarza
    resp_start2 = client.post('/maluchy/api/start', json={'kod_wiadra': '09', 'plan_id': plan_id, 'linia': 'PSD'})
    b2_id = resp_start2.get_json()['bucket']['id']
    client.post('/maluchy/api/item/add', json={'bucket_id': b2_id, 'stacja_kod': 'KO01', 'surowiec_nazwa': 'Sól'})
    client.post('/maluchy/api/complete', json={'bucket_id': b2_id})
    resp_dump2 = client.post('/maluchy/api/dump-to-mixer', json={
        'kod_wiadra': '09',
        'plan_id': plan_id,
        'szarza_id': szarza_id,
        'mieszalnik_kod': 'MI01',
        'linia': 'PSD'
    })
    assert resp_dump2.status_code == 400
    assert 'Do tego zasypu' in resp_dump2.get_json()['message']

    # Test bucket creation & deletion
    resp_del_start = client.post('/maluchy/api/start', json={
        'kod_wiadra': '15',
        'plan_id': plan_id,
        'linia': 'PSD'
    })
    del_bucket_id = resp_del_start.get_json()['bucket']['id']
    resp_del = client.post('/maluchy/api/delete', json={'bucket_id': del_bucket_id})
    assert resp_del.status_code == 200
    assert resp_del.get_json()['success'] is True
