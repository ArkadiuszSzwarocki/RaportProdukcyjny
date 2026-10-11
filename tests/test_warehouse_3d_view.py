"""Warehouse overview opens on the whole hall and retains location navigation."""

import pytest


@pytest.mark.parametrize('path', ['/warehouse-v2/racks-3d', '/warehouse-v2/widok-3d'])
@pytest.mark.parametrize('rack', [None, 'R02'])
def test_overview_default_and_explicit_rack_keep_all_location_buttons(app, path, rack):
    client = app.test_client()
    with client.session_transaction() as session:
        session.update(zalogowany=True, login='pytest', rola='masteradmin', grupa='ALL')
    query = {'linia': 'ALL'}
    if rack:
        query['rack_id'] = rack
    response = client.get(path, query_string=query)
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert f'<option value="{rack or "ALL"}" selected>' in html
    for location in ('R01', 'R02', 'R03', 'R04', 'R05', 'R06', 'R07', 'R09', 'MP01', 'BFMP01'):
        assert f'data-rack-id="{location}"' in html
