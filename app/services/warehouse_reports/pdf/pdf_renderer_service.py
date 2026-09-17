import tempfile
from typing import Optional, Dict, Any

HAS_WEASYPRINT = False
try:
    from weasyprint import HTML
    HAS_WEASYPRINT = True
except (ImportError, OSError):
    HTML = None
    HAS_WEASYPRINT = False


class PdfRendererService:
    """
    Service responsible for converting HTML to PDF or falling back
    to ReportLab when GTK/libgobject is not installed on the system.
    """

    @classmethod
    def render_html_or_fallback(
        cls,
        html_content: str,
        title: str,
        subtitle: str,
        summary_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Renders PDF using WeasyPrint if available, otherwise falls back to ReportLab."""
        tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
        tmp_pdf_path = tmp_pdf.name
        tmp_pdf.close()

        if HAS_WEASYPRINT and HTML is not None:
            try:
                HTML(string=html_content).write_pdf(tmp_pdf_path)
                return tmp_pdf_path
            except Exception as e:
                print(f"WeasyPrint render error: {e}, falling back to reportlab...")

        # Fallback to reportlab
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

            doc = SimpleDocTemplate(
                tmp_pdf_path,
                pagesize=A4,
                leftMargin=30,
                rightMargin=30,
                topMargin=30,
                bottomMargin=30
            )
            styles = getSampleStyleSheet()

            title_style = ParagraphStyle(
                'TitleStyle',
                parent=styles['Heading1'],
                fontSize=16,
                leading=20,
                textColor=colors.HexColor('#0f172a'),
                fontName='Helvetica-Bold'
            )
            subtitle_style = ParagraphStyle(
                'SubtitleStyle',
                parent=styles['Normal'],
                fontSize=10,
                leading=14,
                textColor=colors.HexColor('#475569')
            )

            story = [
                Paragraph(title, title_style),
                Paragraph(subtitle, subtitle_style),
                Spacer(1, 15)
            ]

            if summary_data and 'items' in summary_data:
                table_data = [summary_data.get('headers', ['Lp', 'Produkt', 'Nr Palety', 'Ilość', 'Status'])]
                for row_idx, r in enumerate(summary_data['items'], start=1):
                    table_data.append([str(row_idx)] + [str(col) for col in r])

                t = Table(table_data, repeatRows=1)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#0f172a')),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')])
                ]))
                story.append(t)

            doc.build(story)
            return tmp_pdf_path
        except Exception as e:
            print(f"ReportLab render error: {e}")
            return tmp_pdf_path
