from typing import Dict, Any
from datetime import datetime
from app.services.warehouse_reports.pdf.pdf_renderer_service import PdfRendererService


class TransferPdfBuilder:
    """
    Builder responsible for generating PDF documents for inter-warehouse transfers (OSIP/Centrala).
    """

    @classmethod
    def generate(cls, transfer: Dict[str, Any]) -> str:
        code = transfer.get('transfer_code') or f"TR-{transfer.get('id')}"
        source = transfer.get('source_warehouse') or 'Centrala'
        dest = transfer.get('destination_warehouse') or 'OSIP'
        created_by = transfer.get('created_by') or 'System'
        completed_by = transfer.get('completed_by') or transfer.get('approved_by') or '-'
        c_at = transfer.get('created_at')
        created_str = c_at.strftime('%Y-%m-%d %H:%M') if hasattr(c_at, 'strftime') else str(c_at or '-')
        comp_at = transfer.get('completed_at')
        completed_str = comp_at.strftime('%Y-%m-%d %H:%M') if hasattr(comp_at, 'strftime') else str(comp_at or '-')
        notes = transfer.get('notes') or '-'
        status = transfer.get('status') or 'COMPLETED'
        items = transfer.get('items') or []

        rows_html = ""
        totals_map: Dict[str, Dict[str, Any]] = {}
        total_qty = 0.0

        for idx, it in enumerate(items, start=1):
            pname = (it.get('product_name') or 'Brak nazwy').strip()
            nr_pal = it.get('pallet_sscc') or '-'
            nr_partii = it.get('batch_number') or '-'
            prod_date = str(it.get('production_date') or '-')
            exp_date = str(it.get('expiry_date') or '-')
            qty = float(it.get('loaded_weight') or it.get('requested_weight') or it.get('weight') or 0.0)
            total_qty += qty
            it_status = str(it.get('status') or 'COMPLETED').upper()

            prod_key = pname.lower()
            if prod_key not in totals_map:
                totals_map[prod_key] = {'name': pname, 'count': 0, 'qty': 0.0}
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
                <td style="text-align: center; color: #64748b; font-size: 8px;">{source}</td>
                <td style="text-align: center; font-weight: bold; color: #1e40af; font-size: 8px;">{dest}</td>
                <td style="text-align: center; font-weight: 800; color: #166534;">{it_status}</td>
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
                <td style="text-align: center; font-weight: 800; color: #166534;">PRZYJĘTA</td>
            </tr>
            """

        gen_now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

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
                    border: 2px solid #065f46; border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; background: #f8fafc;
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
                    display: flex; justify-content: space-between; background: #f1f5f9; border: 1.5px solid #94a3b8;
                    border-radius: 6px; padding: 10px 14px; font-weight: 800; font-size: 12px; margin-bottom: 20px;
                }}
                .signatures {{ display: grid; grid-template-columns: 1fr 1fr; gap: 40px; margin-top: 30px; padding-top: 10px; }}
                .sign-box {{ border-top: 1px dashed #64748b; text-align: center; padding-top: 6px; font-size: 10px; font-weight: 700; color: #475569; }}
                .footer {{ margin-top: 25px; font-size: 8px; color: #94a3b8; text-align: center; border-top: 1px solid #e2e8f0; padding-top: 6px; }}
            </style>
        </head>
        <body>
            <div class="header-box">
                <div class="doc-title">
                    <span>Przesunięcie MM ({source} ➔ {dest})</span>
                    <span style="color: #059669;">MM: {code}</span>
                </div>
                <div class="doc-meta">Wygenerowano w systemie produkcyjnym: <strong>{gen_now}</strong> | Status: <strong>ZAKOŃCZONE ({status})</strong></div>
                <div class="grid-4">
                    <div class="meta-item">
                        <div class="meta-label">SKĄD (ŹRÓDŁO)</div>
                        <div class="meta-val">{source}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">DOKĄD (CEL)</div>
                        <div class="meta-val" style="color: #047857;">{dest}</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">WYSTAWIŁ</div>
                        <div class="meta-val">{created_by} ({created_str})</div>
                    </div>
                    <div class="meta-item">
                        <div class="meta-label">PRZYJĄŁ / ZATWIERDZIŁ</div>
                        <div class="meta-val" style="color: #166534;">{completed_by} ({completed_str})</div>
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
                <div>ŁĄCZNIE PRZESUNIĘTO PALET: <span style="color: #059669;">{len(items)} szt.</span></div>
                <div>SUMA ILOŚCI TOWARU: <span style="color: #166534;">{total_qty:,.2f} kg</span></div>
            </div>

            <div class="signatures">
                <div class="sign-box">Podpis wydającego ({created_by.split(' ')[0]})</div>
                <div class="sign-box">Podpis magazyniera przyjmującego ({completed_by.split(' ')[0]})</div>
            </div>

            <div class="footer">
                RaportProdukcyjny — Automatyczny wydruk z systemu magazynowego. Dokument stanowi oficjalne potwierdzenie przesunięcia towaru.
            </div>
        </body>
        </html>
        """

        summary_data = {
            'headers': ['Lp', 'Produkt', 'Nr Palety', 'Partia', 'Ilość', 'Skąd', 'Dokąd', 'Status'],
            'items': [
                [
                    (it.get('product_name') or 'Brak').strip(),
                    it.get('pallet_sscc') or '-',
                    it.get('batch_number') or '-',
                    f"{float(it.get('loaded_weight') or it.get('requested_weight') or it.get('weight') or 0.0):,.2f} kg",
                    source,
                    dest,
                    str(it.get('status') or 'COMPLETED').upper()
                ]
                for it in items
            ]
        }
        title = f"Przesunięcie MM ({source} ➔ {dest}) nr: {code}"
        subtitle = f"Wygenerowano: {gen_now} | Status: {status}"
        return PdfRendererService.render_html_or_fallback(html_content, title, subtitle, summary_data)
