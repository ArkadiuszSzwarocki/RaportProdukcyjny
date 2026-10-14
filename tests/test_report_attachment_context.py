"""A valid generated file must also belong to the requested hall and date."""
from unittest.mock import patch
from flask import Flask
import pytest
from app.core.file_security import _report_attachment_guard


@pytest.mark.parametrize('filename,expected', [
    ('Raport_AGRO_2026-10-03.pdf', 200),
    ('Raport_PSD_2026-10-03.pdf', 400),
    ('Raport_AGRO_2026-10-02.xlsx', 400),
])
def test_attachment_matches_report_context(filename, expected):
    app = Flask(__name__)
    app.add_url_rule('/send', view_func=_report_attachment_guard(lambda: 'OK'), methods=['POST'])
    with patch('app.core.file_security.report_attachment_path_allowed', return_value=True):
        response = app.test_client().post('/send', data={
            'linia': 'AGRO', 'date_str': '2026-10-03', 'attachments': filename})
        assert response.status_code == expected
