"""Quality document permissions never permit downloads outside a plan directory."""
from unittest.mock import patch
import pytest


@pytest.mark.parametrize('filename', ['../../../canary.txt', '..\\..\\canary.txt', 'C:canary.txt'])
def test_quality_download_rejects_escape(client, app, tmp_path, filename):
    folder = tmp_path / 'raporty/jakosc_docs/123'
    folder.mkdir(parents=True)
    (tmp_path / 'canary.txt').write_text('PRIVATE', encoding='utf-8')
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='laborant', pracownik_id=1)
    with patch.object(app, 'root_path', str(tmp_path)), patch(
            'app.core.contexts.inject_role_permissions', return_value={
                'role_has_access': lambda page: page == 'jakosc', 'role_is_readonly': lambda page: False}):
        response = client.get('/jakosc/download/123/' + filename)
        assert response.status_code == 404
        assert b'PRIVATE' not in response.data


def test_quality_download_keeps_valid_document(client, app, tmp_path):
    folder = tmp_path / 'raporty/jakosc_docs/123'
    folder.mkdir(parents=True)
    (folder / 'document.pdf').write_bytes(b'VALID-DOCUMENT')
    with client.session_transaction() as state:
        state.update(zalogowany=True, rola='laborant', pracownik_id=1)
    with patch.object(app, 'root_path', str(tmp_path)), patch(
            'app.core.contexts.inject_role_permissions', return_value={
                'role_has_access': lambda page: page == 'jakosc', 'role_is_readonly': lambda page: False}):
        response = client.get('/jakosc/download/123/document.pdf')
        assert response.status_code == 200
        assert response.data == b'VALID-DOCUMENT'
        response.close()
