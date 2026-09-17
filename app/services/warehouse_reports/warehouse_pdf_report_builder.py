"""
Fasada usług generowania dokumentów PDF A4 dla magazynu.
Deleguje zadania do wyspecjalizowanych builderów (DeliveryPdfBuilder, TransferPdfBuilder, PdfRendererService).
"""
from typing import Dict, Any, List, Optional
from app.services.warehouse_reports.pdf.delivery_pdf_builder import DeliveryPdfBuilder
from app.services.warehouse_reports.pdf.transfer_pdf_builder import TransferPdfBuilder
from app.services.warehouse_reports.pdf.pdf_renderer_service import PdfRendererService


class WarehousePdfReportBuilder:
    """
    Façade for generating warehouse PDF documents (A4).
    Maintains 100% backward compatibility with existing callers.
    """

    @classmethod
    def _render_html_or_fallback(
        cls,
        html_content: str,
        title: str,
        subtitle: str,
        summary_data: Optional[Dict[str, Any]] = None
    ) -> str:
        return PdfRendererService.render_html_or_fallback(html_content, title, subtitle, summary_data)

    @classmethod
    def generate_delivery_pdf(cls, dostawa: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
        """Generuje plik PDF gotowy do druku A4 dla przyjęcia dostawy / przesunięcia MM."""
        return DeliveryPdfBuilder.generate(dostawa, items)

    @classmethod
    def generate_transfer_pdf(cls, transfer: Dict[str, Any]) -> str:
        """Generuje plik PDF gotowy do druku A4 dla transferu międzymagazynowego OSIP."""
        return TransferPdfBuilder.generate(transfer)
