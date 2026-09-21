"""
Moduł odpowiedzialny za generowanie szablonów HTML wiadomości e-mail (raporty dzienne, pojedyncze dostawy i transfery).
"""
from typing import Dict, Any, List
from app.services.warehouse_reports.warehouse_document_classifier import WarehouseDocumentClassifier
from app.services.warehouse_reports.warehouse_status_resolver import WarehouseStatusResolver
from app.services.warehouse_reports.warehouse_activity_query_service import WarehouseActivityQueryService


class WarehouseEmailTemplateBuilder:
    @staticmethod
    def build_single_delivery_html(dostawa: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
        """Buduje raport HTML pojedynczego przyjęcia dostawy/przesunięcia MM."""
        cat = WarehouseDocumentClassifier.categorize_delivery_doc(dostawa, items)
        doc_status = WarehouseStatusResolver.resolve_document_status(dostawa, items)

        rows_html = ""
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
            badge_color = status_info['badge_color']
            badge_bg = status_info['badge_bg']
            status_txt = status_info['status_label']

            rows_html += f"""
            <tr style="border-bottom: 1px solid #f1f5f9;">
                <td style="padding: 10px 12px; text-align: center; color: #64748b; font-weight: 600;">{idx}</td>
                <td style="padding: 10px 12px; font-weight: 700; color: #0f172a;">{pname}</td>
                <td style="padding: 10px 12px; text-align: center; font-family: monospace; font-size: 11px; color: #334155; font-weight: 600;">{nr_pal}</td>
                <td style="padding: 10px 12px; text-align: center; color: #475569;">{nr_partii}</td>
                <td style="padding: 10px 12px; text-align: center; color: #475569;">{prod_date}</td>
                <td style="padding: 10px 12px; text-align: center; color: #475569;">{exp_date}</td>
                <td style="padding: 10px 12px; text-align: right; font-weight: 700; color: #0f172a;">{qty:,.2f} kg</td>
                <td style="padding: 10px 12px; text-align: center; color: #64748b; font-size: 11px;">{source_spot}</td>
                <td style="padding: 10px 12px; text-align: center; font-weight: 700; color: #1e40af; font-size: 11px;">{target_spot}</td>
                <td style="padding: 10px 12px; text-align: center;">
                    <span style="display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 10px; font-weight: 700; background: {badge_bg}; color: {badge_color};">{status_txt}</span>
                </td>
            </tr>
            """

        ref = cat['ref']
        source_label = cat['source_label']
        source_val = cat['source_value']
        dest_label = cat['dest_label']
        dest_val = cat['dest_value']
        creator_label = cat['creator_label']
        creator_val = cat['creator_value']
        acceptor_label = cat['acceptor_label']
        acceptor_val = cat['acceptor_value']
        theme_from = cat['theme_color_from']
        theme_to = cat['theme_color_to']
        notes = dostawa.get('uwagi') or '-'

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px;">
            <div style="max-width: 720px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
                <div style="background: linear-gradient(135deg, {theme_from}, {theme_to}); padding: 24px; color: #ffffff;">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; opacity: 0.85;">{cat['header_title']}</div>
                    <div style="font-size: 22px; font-weight: 900; margin-top: 4px;">{cat['doc_title']}: {source_val} ➔ {dest_val}</div>
                    <div style="font-size: 13px; opacity: 0.9; margin-top: 6px;">Nr dokumentu: <strong>{ref}</strong> | Status: <strong>{doc_status['status_label']}</strong></div>
                </div>

                <div style="padding: 20px 24px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <tr>
                            <td style="color: #64748b; padding: 5px 0; width: 40%;">{source_label}:</td>
                            <td style="font-weight: 700; color: #0f172a; text-align: right;">{source_val}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">{dest_label}:</td>
                            <td style="font-weight: 800; color: #1e40af; text-align: right;">{dest_val}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">{creator_label}:</td>
                            <td style="font-weight: 700; color: #0f172a; text-align: right;">{creator_val}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">{acceptor_label}:</td>
                            <td style="font-weight: 800; color: #166534; text-align: right;">{acceptor_val}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Liczba palet:</td>
                            <td style="font-weight: 800; color: #1e3a8a; text-align: right;">{len(items)} szt.</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Łączna waga przyjęta:</td>
                            <td style="font-weight: 800; color: #166534; text-align: right;">{total_qty:,.2f} kg</td>
                        </tr>
                        {f'<tr><td style="color: #64748b; padding: 5px 0;">Uwagi:</td><td style="font-weight: 600; color: #334155; text-align: right;">{notes}</td></tr>' if notes and notes != '-' else ''}
                    </table>
                </div>

                <div style="padding: 24px 24px 12px 24px;">
                    <div style="font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Wykaz przyjętych palet:</div>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                        <thead>
                            <tr style="background: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                <th style="padding: 10px 12px; text-align: center; width: 35px;">Lp</th>
                                <th style="padding: 10px 12px; text-align: left;">Produkt</th>
                                <th style="padding: 10px 12px; text-align: center;">Nr Palety</th>
                                <th style="padding: 10px 12px; text-align: center;">Partia</th>
                                <th style="padding: 10px 12px; text-align: center;">Data Prod.</th>
                                <th style="padding: 10px 12px; text-align: center;">Data Przyd.</th>
                                <th style="padding: 10px 12px; text-align: right;">Waga</th>
                                <th style="padding: 10px 12px; text-align: center;">Skąd</th>
                                <th style="padding: 10px 12px; text-align: center;">Dokąd</th>
                                <th style="padding: 10px 12px; text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody style="font-size: 12px;">
                            {rows_html}
                        </tbody>
                    </table>
                </div>

                <div style="padding: 16px 24px 24px 24px; text-align: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #f1f5f9;">
                    W załączniku znajduje się oficjalny dokument PDF potwierdzający operację magazynową.
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def build_daily_summary_report_html(date_str: str, activity_data: Dict[str, Any]) -> str:
        """Buduje raport HTML z podsumowaniem dnia z podziałem na Dostawy WZ, Centrala i Przesunięcia MM."""
        deliveries_wz = activity_data.get('deliveries_wz', [])
        deliveries_centrala = activity_data.get('deliveries_centrala', [])
        transfers_mm = activity_data.get('transfers_mm', [])
        all_documents = activity_data.get('all_documents', [])

        total_pallets = activity_data.get('total_pallets', 0)
        total_qty_by_unit = activity_data.get('total_qty_by_unit', {})
        deliveries_wz_products = activity_data.get('deliveries_wz_products_summary', [])
        deliveries_centrala_products = activity_data.get('deliveries_centrala_products_summary', [])
        transfers_mm_products = activity_data.get('transfers_mm_products_summary', [])

        totals_str_parts = [f"<strong>{qty:,.2f} {unit}</strong>" for unit, qty in sorted(total_qty_by_unit.items())]
        totals_display = " + ".join(totals_str_parts) if totals_str_parts else "0.00 kg"

        def _render_doc_cards(docs, border_color="#e2e8f0", header_bg="#f8fafc", badge_bg="#e0e7ff", badge_color="#3730a3"):
            if not docs:
                return f"""
                <div style="padding: 16px; background: #ffffff; border: 1px dashed #cbd5e1; border-radius: 8px; text-align: center; color: #94a3b8; font-size: 13px; margin-bottom: 20px;">
                    Brak zarejestrowanych dokumentów w tej kategorii.
                </div>
                """
            html = ""
            for doc in docs:
                items_rows = ""
                for it in doc.get('items', []):
                    badge_bg_item = "#dcfce7" if it['accepted'] else "#fef3c7"
                    badge_color_item = "#166534" if it['accepted'] else "#b45309"
                    items_rows += f"""
                    <tr style="border-bottom: 1px solid #f1f5f9; font-size: 11px;">
                        <td style="padding: 6px 8px; text-align: center; color: #64748b;">{it['lp']}</td>
                        <td style="padding: 6px 8px; font-weight: 600; color: #0f172a;">{it['product_name']}</td>
                        <td style="padding: 6px 8px; text-align: center; font-family: monospace; font-size: 10px;">{it['nr_palety']}</td>
                        <td style="padding: 6px 8px; text-align: center;">{it['nr_partii']}</td>
                        <td style="padding: 6px 8px; text-align: center;">{it['data_produkcji']}</td>
                        <td style="padding: 6px 8px; text-align: center;">{it['data_przydatnosci']}</td>
                        <td style="padding: 6px 8px; text-align: right; font-weight: 700;">{it['quantity']:,.2f} {it['unit']}</td>
                        <td style="padding: 6px 8px; text-align: center; color: #64748b;">{it['source_spot']}</td>
                        <td style="padding: 6px 8px; text-align: center; font-weight: 700; color: #1e40af;">{it['target_spot']}</td>
                        <td style="padding: 6px 8px; text-align: center;">
                            <span style="display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 9px; font-weight: 700; background: {badge_bg_item}; color: {badge_color_item};">{it['status']}</span>
                        </td>
                    </tr>
                    """

                summary_pills = "".join([
                    f"<span style='display: inline-block; background: #e2e8f0; color: #1e293b; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; margin-right: 6px; margin-bottom: 4px;'>"
                    f"{s['product_name']}: <strong>{s['count']} pal.</strong> ({s['total_qty']:,.2f} {s['unit']})</span>"
                    for s in doc.get('summary', [])
                ])

                html += f"""
                <div style="background: #ffffff; border: 1.5px solid {border_color}; border-radius: 10px; overflow: hidden; margin-bottom: 16px; box-shadow: 0 2px 6px rgba(0,0,0,0.03);">
                    <div style="background: {header_bg}; padding: 12px 16px; border-bottom: 1px solid #e2e8f0; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                        <div>
                            <span style="display: inline-block; background: {badge_bg}; color: {badge_color}; padding: 3px 8px; border-radius: 6px; font-size: 11px; font-weight: 800; text-transform: uppercase; margin-right: 8px;">{doc['doc_title']}</span>
                            <strong style="font-size: 14px; color: #0f172a;">{doc['order_ref']}</strong>
                            <span style="color: #64748b; font-size: 12px; margin-left: 8px;">({doc['source']} ➔ <strong style="color: #1e40af;">{doc['destination']}</strong>)</span>
                        </div>
                        <div style="font-size: 11px; color: #64748b;">
                            Przyjął: <strong style="color: #166534;">{doc['accepted_by']}</strong> ({doc['accepted_str']})
                        </div>
                    </div>

                    <div style="padding: 12px 16px; background: #fcfdfe; border-bottom: 1px solid #f1f5f9;">
                        <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700; margin-bottom: 6px;">Podsumowanie asortymentu w dokumencie:</div>
                        <div>{summary_pills}</div>
                    </div>

                    <div style="padding: 12px 16px;">
                        <div style="font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700; margin-bottom: 8px;">Szczegółowy wykaz palet ({doc['items_count']} szt.):</div>
                        <table style="width: 100%; border-collapse: collapse;">
                            <thead>
                                <tr style="background: #f8fafc; color: #475569; font-size: 10px; text-transform: uppercase; border-bottom: 1px solid #e2e8f0;">
                                    <th style="padding: 6px 8px; text-align: center; width: 25px;">Lp</th>
                                    <th style="padding: 6px 8px; text-align: left;">Produkt</th>
                                    <th style="padding: 6px 8px; text-align: center;">Nr Palety</th>
                                    <th style="padding: 6px 8px; text-align: center;">Partia</th>
                                    <th style="padding: 6px 8px; text-align: center;">Prod.</th>
                                    <th style="padding: 6px 8px; text-align: center;">Przyd.</th>
                                    <th style="padding: 6px 8px; text-align: right;">Ilość</th>
                                    <th style="padding: 6px 8px; text-align: center;">Skąd</th>
                                    <th style="padding: 6px 8px; text-align: center;">Dokąd</th>
                                    <th style="padding: 6px 8px; text-align: center;">Status</th>
                                </tr>
                            </thead>
                            <tbody>
                                {items_rows}
                            </tbody>
                        </table>
                    </div>
                </div>
                """
            return html

        def _render_category_summary_table(summary_items, title, color="#1e3a8a"):
            if not summary_items:
                return f"""
                <div style="padding: 12px; background: #ffffff; border: 1px dashed #cbd5e1; border-radius: 8px; text-align: center; color: #94a3b8; font-size: 12px; margin-bottom: 16px;">
                    Brak pozycji w tej kategorii.
                </div>
                """
            rows = ""
            cat_pallets = 0
            cat_qty_by_unit = {}
            for idx, p in enumerate(summary_items, start=1):
                cat_pallets += p['count']
                u = p['unit']
                cat_qty_by_unit[u] = cat_qty_by_unit.get(u, 0.0) + p['total_qty']
                rows += f"""
                <tr style="border-bottom: 1px solid #f1f5f9; font-size: 12px;">
                    <td style="padding: 8px 10px; text-align: center; color: #64748b;">{idx}</td>
                    <td style="padding: 8px 10px; font-weight: 700; color: #0f172a;">{p['product_name']}</td>
                    <td style="padding: 8px 10px; text-align: center; font-weight: 800; color: {color};">{p['count']} szt.</td>
                    <td style="padding: 8px 10px; text-align: right; font-weight: 800; color: #166534;">{p['total_qty']:,.2f} {p['unit']}</td>
                </tr>
                """
            tot_str = ", ".join([f"{q:,.2f} {u}" for u, q in sorted(cat_qty_by_unit.items())])
            return f"""
            <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; margin-bottom: 16px;">
                <thead>
                    <tr style="background: #f1f5f9; color: #334155; font-size: 11px; text-transform: uppercase;">
                        <th style="padding: 8px 10px; text-align: center; width: 30px;">Lp</th>
                        <th style="padding: 8px 10px; text-align: left;">Produkt</th>
                        <th style="padding: 8px 10px; text-align: center; width: 110px;">Liczba palet</th>
                        <th style="padding: 8px 10px; text-align: right; width: 140px;">Łączna ilość</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                    <tr style="background: #f8fafc; font-weight: 800; border-top: 2px solid #cbd5e1; font-size: 12px;">
                        <td colspan="2" style="padding: 10px; text-align: right; text-transform: uppercase;">Razem {title}:</td>
                        <td style="padding: 10px; text-align: center; color: {color};">{cat_pallets} szt.</td>
                        <td style="padding: 10px; text-align: right; color: #166534;">{tot_str}</td>
                    </tr>
                </tbody>
            </table>
            """

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px;">
            <div style="max-width: 960px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
                <div style="background: linear-gradient(135deg, #1e3a8a, #0f172a); padding: 28px; color: #ffffff;">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; opacity: 0.85;">Raport Dzienny — Gospodarka Magazynowa</div>
                    <div style="font-size: 24px; font-weight: 900; margin-top: 4px;">📊 Zestawienie Ruchów Magazynowych z Dnia: {date_str}</div>
                    <div style="font-size: 13px; opacity: 0.9; margin-top: 6px;">Raport zbiorczy: Dostawy Zewnętrzne (WZ) • Dostawy Centrala • Przesunięcia MM</div>
                </div>

                <div style="padding: 20px 24px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;">
                        <div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; text-align: center;">
                            <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">Dostawy Zewn. (WZ)</div>
                            <div style="font-size: 20px; font-weight: 900; color: #1e40af; margin-top: 4px;">{len(deliveries_wz)}</div>
                        </div>
                        <div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; text-align: center;">
                            <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">Dostawy Centrala</div>
                            <div style="font-size: 20px; font-weight: 900; color: #0284c7; margin-top: 4px;">{len(deliveries_centrala)}</div>
                        </div>
                        <div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; text-align: center;">
                            <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">Przesunięcia MM</div>
                            <div style="font-size: 20px; font-weight: 900; color: #059669; margin-top: 4px;">{len(transfers_mm)}</div>
                        </div>
                        <div style="background: #ffffff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 12px; text-align: center;">
                            <div style="font-size: 10px; font-weight: 700; color: #64748b; text-transform: uppercase;">Łącznie Palet</div>
                            <div style="font-size: 20px; font-weight: 900; color: #0f172a; margin-top: 4px;">{total_pallets} szt.</div>
                        </div>
                    </div>
                </div>

                <div style="padding: 24px;">
                    <div style="font-size: 16px; font-weight: 900; color: #1e3a8a; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">
                        📦 1. Dostawy Zewnętrzne (WZ) ({len(deliveries_wz)})
                    </div>
                    {_render_doc_cards(deliveries_wz, border_color="#bfdbfe", header_bg="#eff6ff", badge_bg="#dbeafe", badge_color="#1e40af")}

                    <div style="font-size: 16px; font-weight: 900; color: #0284c7; margin-top: 28px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">
                        🏢 2. Dostawa Centrala ({len(deliveries_centrala)})
                    </div>
                    {_render_doc_cards(deliveries_centrala, border_color="#bae6fd", header_bg="#f0f9ff", badge_bg="#e0f2fe", badge_color="#0369a1")}

                    <div style="font-size: 16px; font-weight: 900; color: #065f46; margin-top: 28px; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">
                        🔄 3. Przesunięcia Międzymagazynowe (MM) ({len(transfers_mm)})
                    </div>
                    {_render_doc_cards(transfers_mm, border_color="#a7f3d0", header_bg="#ecfdf5", badge_bg="#d1fae5", badge_color="#065f46")}

                    <div style="font-size: 18px; font-weight: 900; color: #0f172a; margin-top: 36px; margin-bottom: 16px; text-transform: uppercase; letter-spacing: 0.5px; border-top: 2px solid #e2e8f0; padding-top: 24px;">
                        📈 4. Podsumowanie Asortymentowe
                    </div>

                    <div style="font-size: 13px; font-weight: 800; color: #1e40af; margin-bottom: 8px; text-transform: uppercase;">
                        📦 4.1. Dostawy Zewnętrzne (WZ) ({len(deliveries_wz_products)})
                    </div>
                    {_render_category_summary_table(deliveries_wz_products, "Dostawy Zewnętrzne", color="#1e40af")}

                    <div style="font-size: 13px; font-weight: 800; color: #0284c7; margin-top: 20px; margin-bottom: 8px; text-transform: uppercase;">
                        🏢 4.2. Dostawa Centrala ({len(deliveries_centrala_products)})
                    </div>
                    {_render_category_summary_table(deliveries_centrala_products, "Dostawy Centrala", color="#0284c7")}

                    <div style="font-size: 13px; font-weight: 800; color: #065f46; margin-top: 20px; margin-bottom: 8px; text-transform: uppercase;">
                        🔄 4.3. Przesunięcia Międzymagazynowe MM ({len(transfers_mm_products)})
                    </div>
                    {_render_category_summary_table(transfers_mm_products, "Przesunięcia MM", color="#065f46")}
                </div>

                <div style="padding: 16px 24px; background: #f8fafc; border-top: 1px solid #e2e8f0; text-align: center; font-size: 11px; color: #64748b;">
                    Do wiadomości załączono {len(all_documents)} oficjalnych plików PDF (kart przyjęć i przesunięć MM gotowych do druku A4).
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def build_transfer_report_html(transfer: Any) -> str:
        """Buduje raport HTML po przyjęciu Transferu Wewnętrznego OSIP."""
        code = getattr(transfer, 'transfer_code', '') or f"TR-{getattr(transfer, 'id', '')}"
        source = getattr(transfer, 'source_warehouse', '') or 'Centrala'
        dest = getattr(transfer, 'destination_warehouse', '') or 'OSIP'
        created_by = getattr(transfer, 'created_by', '') or getattr(transfer, 'dispatched_by', '') or 'System'
        completed_by = getattr(transfer, 'completed_by', None) or getattr(transfer, 'updated_by', None) or '-'

        created_at = getattr(transfer, 'created_at', None)
        completed_at = getattr(transfer, 'completed_at', None) or getattr(transfer, 'updated_at', None) or created_at

        created_str = created_at.strftime('%Y-%m-%d %H:%M') if created_at and hasattr(created_at, 'strftime') else (str(created_at) if created_at else '-')
        completed_str = completed_at.strftime('%Y-%m-%d %H:%M') if completed_at and hasattr(completed_at, 'strftime') else (str(completed_at) if completed_at else '-')

        status = getattr(transfer, 'status', 'COMPLETED')
        notes = getattr(transfer, 'notes', '') or '-'

        raw_items = getattr(transfer, 'items', []) or []
        items = raw_items if isinstance(raw_items, list) else []

        total_qty = 0.0
        total_pallets = len(items)
        rows_html = ""
        for idx, it in enumerate(items, start=1):
            prod = getattr(it, 'product_name', None) or (it.get('product_name') if isinstance(it, dict) else 'Brak nazwy')
            nr_pal = getattr(it, 'nr_palety', None) or (it.get('nr_palety') if isinstance(it, dict) else '-')
            batch = getattr(it, 'batch_number', None) or (it.get('batch_number') if isinstance(it, dict) else '-')
            qty = float(getattr(it, 'loaded_qty', 0.0) or getattr(it, 'requested_qty', 0.0) or (it.get('loaded_qty', 0.0) if isinstance(it, dict) else it.get('requested_qty', 0.0)) or 0.0)
            unit = getattr(it, 'unit', 'kg') or (it.get('unit', 'kg') if isinstance(it, dict) else 'kg')
            it_status = getattr(it, 'status', 'RECEIVED') or (it.get('status') if isinstance(it, dict) else 'RECEIVED')
            total_qty += qty

            rows_html += f"""
            <tr style="border-bottom: 1px solid #e2e8f0; font-size: 13px;">
                <td style="padding: 10px 12px; text-align: center; color: #64748b; font-weight: 600;">{idx}</td>
                <td style="padding: 10px 12px; font-weight: 700; color: #0f172a;">{prod}</td>
                <td style="padding: 10px 12px; font-family: monospace; font-weight: 700; color: #1e293b; background: #f8fafc; text-align: center;">{nr_pal}</td>
                <td style="padding: 10px 12px; text-align: center; color: #475569;">{batch}</td>
                <td style="padding: 10px 12px; text-align: right; font-weight: 800; color: #166534;">{qty:,.2f} {unit}</td>
                <td style="padding: 10px 12px; text-align: center;"><span style="display:inline-block; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; background: #dcfce7; color: #15803d;">{it_status}</span></td>
            </tr>
            """

        if not rows_html:
            rows_html = '<tr><td colspan="6" style="padding: 16px; text-align: center; color: #64748b;">Brak pozycji w zleceniu.</td></tr>'

        return f"""
        <!DOCTYPE html>
        <html>
        <head><meta charset="utf-8"></head>
        <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 24px;">
            <div style="max-width: 720px; margin: 0 auto; background: #ffffff; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
                <div style="background: linear-gradient(135deg, #1e1b4b, #4338ca); padding: 24px; color: #ffffff;">
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 1px; font-weight: 700; opacity: 0.85;">Raport Przyjęcia Transferu Towaru</div>
                    <div style="font-size: 22px; font-weight: 900; margin-top: 4px;">🚚 Transfer: {source} ➔ {dest}</div>
                    <div style="font-size: 13px; opacity: 0.9; margin-top: 6px;">Kod zlecenia: <strong>{code}</strong> | Status: <strong>PRZYJĘTE ({status})</strong></div>
                </div>

                <div style="padding: 20px 24px; background: #f8fafc; border-bottom: 1px solid #e2e8f0;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <tr>
                            <td style="color: #64748b; padding: 5px 0; width: 40%;">Magazyn wydający (Skąd):</td>
                            <td style="font-weight: 700; color: #0f172a; text-align: right;">{source}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Magazyn docelowy (Dokąd):</td>
                            <td style="font-weight: 800; color: #4338ca; text-align: right;">{dest}</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Otworzył / Wydał:</td>
                            <td style="font-weight: 700; color: #0f172a; text-align: right;">{created_by} ({created_str})</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Przyjął / Zatwierdził:</td>
                            <td style="font-weight: 800; color: #166534; text-align: right;">{completed_by} ({completed_str})</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Liczba palet:</td>
                            <td style="font-weight: 800; color: #4338ca; text-align: right;">{total_pallets} szt.</td>
                        </tr>
                        <tr>
                            <td style="color: #64748b; padding: 5px 0;">Łączna ilość przyjęta:</td>
                            <td style="font-weight: 800; color: #166534; text-align: right;">{total_qty:,.2f} kg</td>
                        </tr>
                        {f'<tr><td style="color: #64748b; padding: 5px 0;">Uwagi do transferu:</td><td style="font-weight: 600; color: #334155; text-align: right;">{notes}</td></tr>' if notes and notes != '-' else ''}
                    </table>
                </div>

                <div style="padding: 24px 24px 12px 24px;">
                    <div style="font-size: 14px; font-weight: 800; color: #0f172a; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.5px;">Wykaz przyjętych palet:</div>
                    <table style="width: 100%; border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden;">
                        <thead>
                            <tr style="background: #f1f5f9; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                <th style="padding: 10px 12px; text-align: center; width: 35px;">Lp</th>
                                <th style="padding: 10px 12px; text-align: left;">Produkt</th>
                                <th style="padding: 10px 12px; text-align: center;">Nr Palety</th>
                                <th style="padding: 10px 12px; text-align: center;">Partia</th>
                                <th style="padding: 10px 12px; text-align: right;">Ilość</th>
                                <th style="padding: 10px 12px; text-align: center;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows_html}
                        </tbody>
                    </table>
                </div>

                <div style="padding: 16px 24px 24px 24px; text-align: center; font-size: 11px; color: #94a3b8; border-top: 1px solid #f1f5f9;">
                    W załączniku znajduje się oficjalny dokument PDF potwierdzający przyjęcie transferu w systemie RaportProdukcyjny.
                </div>
            </div>
        </body>
        </html>
        """
