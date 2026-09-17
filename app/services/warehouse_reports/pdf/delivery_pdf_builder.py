from typing import Dict, Any, List
from datetime import datetime
from app.services.warehouse_reports.warehouse_document_classifier import WarehouseDocumentClassifier
from app.services.warehouse_reports.warehouse_status_resolver import WarehouseStatusResolver
from app.services.warehouse_reports.warehouse_activity_query_service import WarehouseActivityQueryService
from app.services.warehouse_reports.pdf.pdf_renderer_service import PdfRendererService


class DeliveryPdfBuilder:
    """
    Builder responsible for generating PDF documents for external deliveries (PZ)
    and internal transfers (MM).
    """

    @classmethod
    def generate(cls, dostawa: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
        cat = WarehouseDocumentClassifier.categorize_delivery_doc(dostawa, items)
        doc_status = WarehouseStatusResolver.resolve_document_status(dostawa, items)

        rows_html = ""
        totals_map: Dict[str, Dict[str, Any]] = {}
        total_qty = 0.0

        for idx, it in enumerate(items, start=1):
            pname = it.get('productName') or 'Brak nazwy'
            nr_pal = it.get('nr_palety') or '-'
            nr_partii = it.get('nr_partii') or '-'
            prod_date = it.get('data_produkcji') or '-'
            exp_date = it.get('data_przydatnosci') or '-'
            qty = WarehouseActivityQueryService.extract_item_qty(it)
            total_qty += qty

            source_spot = it.get('sourceSpot') or cat['source_value']
            target_spot = it.get('lokalizacja_przyjecia') or it.get('targetSpot') or cat['dest_value']
            if not target_spot or target_spot == 'OCZEKUJĄCE':
                target_spot = cat['dest_value']

            status_info = WarehouseStatusResolver.resolve_item_status(it, dostawa.get('status'))
            status_txt = status_info['status_label']
            badge_color = status_info['badge_color']

            prod_key = pname.lower().strip()
            if prod_key not in totals_map:
                totals_map[prod_key] = {'name': pname, 'count': 0, 'qty': 0.0, 'status': status_txt}
            totals_map[prod_key]['count'] += 1
            totals_map[prod_key]['qty'] += qty

            rows_html += f"""
            <tr>
                <td style="text-align: center; font-weight: bold; color: #64748b;">{idx}</td>
                <td style="font-weight: 700; color: #0f172a;">{pname}</td>
                <td style="text-align: center; font-family: monospace; font-size: 8px; font-weight: bold;">{nr_pal}</td>
                <td style="text-align: center;">{nr_partii}</td>
                <td style="text-align: center;">{prod_date}</td>
                <td style="text-align: center;">{exp_date}</td>
                <td style="text-align: right; font-weight: 800;">{qty:,.2f} kg</td>
                <td style="text-align: center; color: #64748b; font-size: 8px;">{source_spot}</td>
                <td style="text-align: center; font-weight: bold; color: #1e40af; font-size: 8px;">{target_spot}</td>
                <td style="text-align: center; font-weight: 800; color: {badge_color};">{status_txt}</td>
            </tr>
            """

        summary_rows_html = ""
        for s_idx, (k, v) in enumerate(totals_map.items(), start=1):
            summary_rows_html += f"""
            <tr>
                <td style="text-align: center; font-weight: bold; color: #64748b;">{s_idx}</td>
                <td style="font-weight: 700; color: #0f172a;">{v['name']}</td>
                <td style="text-align: center; font-weight: 800; color: #1e3a8a;">{v['count']} szt.</td>
                <td style="text-align: right; font-weight: 800; color: #166534;">{v['qty']:,.2f} kg</td>
                <td style="text-align: center; font-weight: 800; color: #166534;">{v['status']}</td>
            </tr>
            """

        gen_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ref = cat['ref']
        creator_val = cat['creator_value']
        acceptor_val = cat['acceptor_value']

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                @page {{ size: A4 portrait; margin: 10mm 10mm 10mm 10mm; }}
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
                    font-size: 9px; line-height: 1.25; color: #0f172a; margin: 0; padding: 0;
                }}
                .header-box {{
                    border: 2px solid #1e3a8a; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; background: #f8fafc;
                }}
                .doc-title {{
                    font-size: 18px; font-weight: 900; text-transform: uppercase; letter-spacing: 0.5px;
                    margin: 0 0 6px 0; color: #0f172a; display: flex; justify-content: space-between; align-items: center;
                }}
                .doc-meta {{ font-size: 11px; color: #475569; margin-bottom: 8px; }}
                .grid-4 {{
                    display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px; padding-top: 8px; border-top: 1px solid #cbd5e1;
                }}
                .meta-item {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px 8px; }}
                .meta-label {{ font-size: 9px; text-transform: uppercase; color: #64748b; font-weight: 700; margin-bottom: 2px; }}
                .meta-val {{ font-size: 11px; font-weight: 800; color: #0f172a; word-break: break-word; }}
                table.data-table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                table.data-table th, table.data-table td {{ border: 1px solid #cbd5e1; padding: 6px 6px; }}
                table.data-table th {{
                    background: #e2e8f0; color: #1e293b; font-weight: 800; text-transform: uppercase; font-size: 9px; letter-spacing: 0.3px;
                }}
                table.data-table tr:nth-child(even) {{ background: #f8fafc; }}
                .summary-box {{
                    display: flex; justify-content: space-between; background: #f1f5f9; border: 1.5px solid #94a3b8; border-radius: 6px; padding: 10px 14px;
                    font-size: 11px; font-weight: 800; margin-top: 12px;
                }}
                .signatures {{ display: grid; grid-template-columns: 1fr 1fr; gap: 40px; margin-top: 30px; padding-top: 10px; }}
                .sign-box {{ border-top: 1px dashed #64748b; text-align: center; padding-top: 6px; font-size: 10px; font-weight: 700; color: #475569; }}
                .footer {{ margin-top: 25px; font-size: 8px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 6px; }}
            </style>
        </head>
        <body>
            <div class="header-box">
                <div class="doc-title">
                    <span>{cat['doc_title']}</span>
                    <span style="color: #2563eb;">WZ/Nr: {ref}</span>
                </div>
                <div class="doc-meta">Wygenerowano w systemie produkcyjnym: <strong>{gen_now}</strong> | Status: <strong>{doc_status['status_label']}</strong></div>
                <div class="grid-4">
                    <div class="meta-item">
                        <div class="meta-label">{cat['source_label']}</div>
                        <div class="meta-val">{cat['source_value']}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">{cat['dest_label']}</div>
                        <div class="meta-val" style="color: #1e40af;">{cat['dest_value']}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">{cat['creator_label']}</div>
                        <div class="meta-val">{cat['creator_value']}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">{cat['acceptor_label']}</div>
                        <div class="meta-val" style="color: #166534;">{cat['acceptor_value']}</div>
                    </div>
                </div>
            </div>

            <table class="data-table">
                <thead>
                    <tr>
                        <th style="width: 25px; text-align: center;">Lp</th>
                        <th style="text-align: left;">Produkt</th>
                        <th style="text-align: center;">Nr Palety (SSCC)</th>
                        <th style="text-align: center;">Partia</th>
                        <th style="text-align: center;">Data Prod.</th>
                        <th style="text-align: center;">Data Przyd.</th>
                        <th style="text-align: right;">Ilość</th>
                        <th style="text-align: center;">Skąd</th>
                        <th style="text-align: center;">Dokąd</th>
                        <th style="text-align: center;">Status</th>
                    </tr>
                </thead>
                <tbody>{rows_html}</tbody>
            </table>

            <div style="font-size: 11px; font-weight: 800; color: #0f172a; margin-top: 14px; margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.5px;">
                PODSUMOWANIE ZBIORCZE WEDŁUG PRODUKTÓW:
            </div>
            <table class="data-table">
                <thead>
                    <tr>
                        <th style="width: 25px; text-align: center;">Lp</th>
                        <th style="text-align: left;">Nazwa Produktu</th>
                        <th style="width: 120px; text-align: center;">Liczba Palet</th>
                        <th style="width: 140px; text-align: right;">Łączna Ilość</th>
                        <th style="width: 100px; text-align: center;">Status</th>
                    </tr>
                </thead>
                <tbody>
                    {summary_rows_html}
                    <tr style="background: #f1f5f9; font-weight: 800;">
                        <td colspan="2" style="text-align: right; text-transform: uppercase;">ŁĄCZNIE:</td>
                        <td style="text-align: center; color: #1e3a8a;">{len(items)} szt.</td>
                        <td style="text-align: right; color: #166534;">{total_qty:,.2f}</td>
                        <td></td>
                    </tr>
                </tbody>
            </table>

            <div class="summary-box" style="margin-top: 14px;">
                <div>ŁĄCZNIE PRZYJĘTO PALET: <span style="color: #2563eb;">{len(items)} szt.</span></div>
                <div>SUMA ILOŚCI TOWARU: <span style="color: #166534;">{total_qty:,.2f} kg</span></div>
            </div>

            <div class="signatures">
                <div class="sign-box">Podpis wydającego / kierowcy ({creator_val.split(' ')[0]})</div>
                <div class="sign-box">Podpis magazyniera przyjmującego ({acceptor_val.split(' ')[0]})</div>
            </div>

            <div class="footer">
                RaportProdukcyjny — Automatyczny wydruk z systemu magazynowego. Dokument stanowi oficjalne potwierdzenie przyjęcia towaru.
            </div>
        </body>
        </html>
        """

        summary_data = {
            'headers': ['Lp', 'Produkt', 'Nr Palety', 'Partia', 'Ilość', 'Skąd', 'Dokąd', 'Status'],
            'items': [
                [
                    it.get('productName') or 'Brak',
                    it.get('nr_palety') or '-',
                    it.get('nr_partii') or '-',
                    f"{WarehouseActivityQueryService.extract_item_qty(it):,.2f} kg",
                    it.get('sourceSpot') or cat['source_value'],
                    it.get('lokalizacja_przyjecia') or cat['dest_value'],
                    WarehouseStatusResolver.resolve_item_status(it, dostawa.get('status'))['status_label']
                ]
                for it in items
            ]
        }
        title = f"{cat.get('doc_title', 'Dokument')} nr: {cat.get('ref', '-')}"
        subtitle = f"Trasa: {cat.get('source_value', '-')} ➔ {cat.get('dest_value', '-')} | Status: {doc_status.get('status_label', '-')}"
        return PdfRendererService.render_html_or_fallback(html_content, title, subtitle, summary_data)
