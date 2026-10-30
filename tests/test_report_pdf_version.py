from unittest.mock import patch
import pytest
from app.services.report_pdf_version import REPORT_LAYOUT_ID,verify_pdf_layout

@pytest.mark.parametrize('content',[b'%PDF-1.4 old layout',b'not a pdf'])
def test_rejects_old_or_invalid_pdf_before_sending(content):
    with patch('pathlib.Path.read_bytes',return_value=content):
        with pytest.raises(ValueError):verify_pdf_layout('report.pdf')

def test_accepts_current_layout_and_identifies_exact_attachment():
    content=b'%PDF-1.4 /Subject ('+REPORT_LAYOUT_ID.encode()+b')'
    with patch('pathlib.Path.read_bytes',return_value=content):
        assert len(verify_pdf_layout('report.pdf'))==64
