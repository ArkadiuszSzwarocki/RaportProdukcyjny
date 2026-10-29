"""Reject outdated PDF layouts before automatic email dispatch."""
import hashlib
import logging
from pathlib import Path

REPORT_LAYOUT_ID='shift-layout-2026-10-29-v1'
logger=logging.getLogger(__name__)

def verify_pdf_layout(path):
    pdf=Path(path)
    content=pdf.read_bytes()
    if not content.startswith(b'%PDF-') or REPORT_LAYOUT_ID.encode('ascii') not in content:
        raise ValueError('PDF ma starszy lub nieznany układ. Wysyłka wstrzymana; proces raportów wymaga aktualizacji.')
    digest=hashlib.sha256(content).hexdigest()
    logger.info('[REPORT_PDF] layout=%s sha256=%s file=%s size=%s',REPORT_LAYOUT_ID,digest,pdf.name,len(content))
    return digest
