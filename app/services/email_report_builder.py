"""
Serwis do budowania profesjonalnych, graficznych szablonów wiadomości e-mail (HTML) dla raportów produkcyjnych.
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, date


class EmailReportBuilder:
    """Buduje elegancki, responsywny kod HTML wiadomości e-mail z raportem produkcyjnym."""

    @staticmethod
    def build_shift_report_html(
        linia: str,
        date_str: str,
        lider_name: str,
        suma_zasyp: int,
        suma_workowanie: int,
        downtimes: List[Dict[str, Any]],
        total_downtime_min: int,
        notes_text: str,
        attachments_names: Optional[List[str]] = None,
        **kwargs
    ) -> str:
        """Generuje pełny graficzny szablon HTML wiadomości e-mail z kartami KPI i tabelą."""
        
        dt_hours = total_downtime_min // 60
        dt_mins = total_downtime_min % 60
        if dt_hours > 0:
            downtime_str = f"{dt_hours}h {dt_mins} min ({total_downtime_min} min)"
        else:
            downtime_str = f"{dt_mins} min"

        # Obliczenie wydajności Zasypu: kg / (480 min - awarie zasypu) * 60 min
        zasyp_dt_min = 0
        if downtimes:
            for dt in downtimes:
                if (dt.get('sekcja') or '').strip().lower() == 'zasyp':
                    dur_val = dt.get('czas_trwania_min')
                    if dur_val is not None:
                        try:
                            zasyp_dt_min += int(dur_val)
                        except: pass
        from app.services.shift_time_service import ShiftTimeService
        prod_metrics = ShiftTimeService.calculate_productivity(
            mass_kg=suma_zasyp,
            awarie_min=zasyp_dt_min,
            date_str=date_str
        )
        zasyp_brutto_min = prod_metrics['brutto_min']
        zasyp_netto_min = prod_metrics['netto_min']
        wyd_efekt_str = f"{prod_metrics['wydajnosc_efektywna']:.1f} kg/h"
        wyd_rzecz_str = f"{prod_metrics['wydajnosc_rzeczywista']:.1f} kg/h"
        start_str = prod_metrics['start_str']
        end_str = prod_metrics['end_str']

        # Generowanie wierszy tabeli przestojów
        downtime_rows_html = ""
        if downtimes:
            for idx, dt in enumerate(downtimes, 1):
                sek = dt.get('sekcja') or 'Produkcja'
                kat = dt.get('kategoria') or 'Inne'
                op = dt.get('opis') or ''
                g_start = str(dt.get('godzina_start') or '')[:5]
                g_stop = str(dt.get('godzina_stop') or '')[:5] if dt.get('godzina_stop') else 'trwa'
                dur = dt.get('czas_trwania_min')
                dur_txt = f"{dur} min" if dur is not None else "w toku"
                prod = dt.get('produkt') or ''

                bg_color = "#ffffff" if idx % 2 != 0 else "#f8fafc"
                
                # Kolor badge'a sekcji
                badge_bg = "#e0f2fe" if sek.lower() == 'zasyp' else "#dcfce7"
                badge_color = "#0369a1" if sek.lower() == 'zasyp' else "#166534"

                downtime_rows_html += f"""
                <tr style="background-color: {bg_color}; border-bottom: 1px solid #e2e8f0;">
                    <td style="padding: 10px 12px; font-size: 13px; color: #0f172a; text-align: center; font-weight: bold;">{idx}</td>
                    <td style="padding: 10px 12px; font-size: 13px;">
                        <span style="background-color: {badge_bg}; color: {badge_color}; padding: 3px 8px; border-radius: 6px; font-weight: bold; font-size: 11px; text-transform: uppercase;">
                            {sek}
                        </span>
                    </td>
                    <td style="padding: 10px 12px; font-size: 13px; color: #334155; white-space: nowrap;">{g_start} – {g_stop}</td>
                    <td style="padding: 10px 12px; font-size: 13px; font-weight: bold; color: #dc2626; text-align: center;">{dur_txt}</td>
                    <td style="padding: 10px 12px; font-size: 13px; color: #0f172a;">
                        <strong>{kat}</strong>: {op}
                        {f'<div style="font-size: 11px; color: #64748b; margin-top: 2px;">Zlecenie: <em>{prod}</em></div>' if prod else ''}
                    </td>
                </tr>
                """
        else:
            downtime_rows_html = """
            <tr>
                <td colspan="5" style="padding: 16px; text-align: center; color: #64748b; font-size: 13px; background-color: #f8fafc;">
                    ✅ Brak zarejestrowanych przestojów i awarii w trakcie zmiany.
                </td>
            </tr>
            """

        # Generowanie sekcji przestojów (ukrywana jeśli brak)
        downtime_section_html = ""
        if downtimes and len(downtimes) > 0:
            downtime_section_html = f"""
            <!-- SECTION 2: DOWNTIMES SUMMARY BAR -->
            <div style="background-color: #fffbeb; border: 1.5px solid #fde68a; border-left: 5px solid #f59e0b; border-radius: 10px; padding: 14px 18px; margin-bottom: 24px;">
                <table width="100%" border="0" cellspacing="0" cellpadding="0">
                    <tr>
                        <td>
                            <div style="font-size: 11px; font-weight: 800; color: #b45309; text-transform: uppercase;">
                                ⚠️ Podsumowanie Przestojów i Awarii:
                            </div>
                            <div style="font-size: 16px; font-weight: 800; color: #78350f; margin-top: 2px;">
                                Łączny czas przestoju: <span style="color: #dc2626;">{downtime_str}</span>
                            </div>
                        </td>
                        <td align="right" style="font-size: 13px; color: #92400e; font-weight: 700;">
                            Zdarzeń: <span style="background-color: #fef3c7; border: 1px solid #fcd34d; padding: 3px 8px; border-radius: 999px;">{len(downtimes)}</span>
                        </td>
                    </tr>
                </table>
            </div>

            <!-- SECTION 3: DOWNTIMES TABLE -->
            <div style="font-size: 13px; font-weight: 800; color: #475569; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 10px;">
                📋 Rejestr Przestojów i Zdarzeń:
            </div>
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="border-collapse: collapse; border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; margin-bottom: 24px;">
                <thead>
                    <tr style="background-color: #f8fafc; border-bottom: 1.5px solid #e2e8f0; color: #475569; font-size: 11px; font-weight: 800; text-transform: uppercase;">
                        <th style="padding: 8px 12px; text-align: center;">#</th>
                        <th style="padding: 8px 12px; text-align: left;">Sekcja</th>
                        <th style="padding: 8px 12px; text-align: left;">Godziny</th>
                        <th style="padding: 8px 12px; text-align: center;">Czas</th>
                        <th style="padding: 8px 12px; text-align: left;">Kategoria / Opis</th>
                    </tr>
                </thead>
                <tbody>
                    {downtime_rows_html}
                </tbody>
            </table>
            """

        # Generowanie sekcji notatek (ukrywana jeśli pusta)
        czyste_notatki = (notes_text or "").replace("NOTATKI ZMIANOWE:\n", "").replace("-" * 50 + "\n", "").lstrip('|').strip()
        notes_section_html = ""
        if czyste_notatki and czyste_notatki.lower() != "brak uwag i notatek lidera.":
            formatted_notes = czyste_notatki.replace("\n", "<br>")
            notes_section_html = f"""
            <!-- SECTION 4: NOTES -->
            <div style="font-size: 13px; font-weight: 800; color: #475569; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;">
                📝 Notatki Zmianowe i Uwagi Lidera:
            </div>
            <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-left: 4px solid #3b82f6; border-radius: 8px; padding: 14px 18px; font-size: 13px; color: #1e293b; line-height: 1.6; margin-bottom: 20px;">
                {formatted_notes}
            </div>
            """

        # Generowanie listy załączników z automatyczną informacją
        att_html = ""
        if attachments_names:
            att_items = "".join([f'<li style="margin-bottom: 5px; color: #334155;">📎 <strong>{name}</strong></li>' for name in attachments_names])
            att_html = f"""
            <div style="margin-top: 20px; padding: 16px 20px; background-color: #eff6ff; border: 1.5px solid #bfdbfe; border-left: 5px solid #2563eb; border-radius: 10px;">
                <div style="font-size: 13px; font-weight: 800; color: #1e40af; margin-bottom: 6px; display: flex; align-items: center; gap: 6px;">
                    ℹ️ Więcej szczegółowych informacji w załącznikach do wiadomości:
                </div>
                <div style="font-size: 12px; color: #475569; margin-bottom: 10px; line-height: 1.4;">
                    Szczegółowy przebieg produkcji, pozycje zleceń, czasy cykli, obsada pracownicza oraz ewidencja surowców znajdują się w wygenerowanych plikach:
                </div>
                <ul style="margin: 0; padding-left: 18px; font-size: 13px;">
                    {att_items}
                </ul>
            </div>
            """
        else:
            att_html = """
            <div style="margin-top: 20px; padding: 14px 18px; background-color: #eff6ff; border: 1px solid #bfdbfe; border-left: 4px solid #2563eb; border-radius: 8px; font-size: 13px; color: #1e40af;">
                ℹ️ <strong>Więcej informacji</strong> znajduje się w szczegółowym raporcie w załącznikach (PDF / Excel).
            </div>
            """

        # Bezpieczne sformatowanie notatek
        formatted_notes = (notes_text or "Brak dodatkowych uwag lidera.").replace("\n", "<br>")

        # Kompletny szablon HTML e-maila
        return f"""
        <!DOCTYPE html>
        <html lang="pl">
        <head>
            <meta charset="utf-8">
            <title>Raport Produkcyjny {linia} — {date_str}</title>
        </head>
        <body style="margin: 0; padding: 20px; background-color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #0f172a; line-height: 1.5;">
            
            <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 680px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 20px rgba(15, 23, 42, 0.08); border: 1px solid #e2e8f0;">
                
                <!-- HEADER -->
                <tr>
                    <td style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 28px 30px; color: #ffffff;">
                        <table width="100%" border="0" cellspacing="0" cellpadding="0">
                            <tr>
                                <td>
                                    <div style="font-size: 12px; font-weight: 800; color: #38bdf8; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px;">
                                        SYSTEM RAPORT PRODUKCYJNY
                                    </div>
                                    <h1 style="margin: 0; font-size: 22px; font-weight: 800; color: #ffffff; line-height: 1.2;">
                                        📊 Raport Zmiany — Linia {linia}
                                    </h1>
                                    <div style="margin-top: 8px; font-size: 13px; color: #94a3b8;">
                                        📅 Data: <strong style="color: #ffffff;">{date_str}</strong> &nbsp;|&nbsp; 👤 Lider: <strong style="color: #ffffff;">{lider_name}</strong>
                                    </div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>

                <!-- CONTENT -->
                <tr>
                    <td style="padding: 26px 30px;">
                        
                        <!-- SECTION 1: KPI TILES (ZASYP & WORKOWANIE) -->
                        <div style="font-size: 13px; font-weight: 800; color: #475569; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 12px;">
                            📈 Produkcja na Zmianie:
                        </div>
                        
                        <table width="100%" border="0" cellspacing="0" cellpadding="0" style="margin-bottom: 24px;">
                            <tr>
                                <!-- Zasyp (Wytworzono) -->
                                <td width="48%" style="background-color: #f0f9ff; border: 1.5px solid #bae6fd; border-radius: 12px; padding: 18px; text-align: center;">
                                     <div style="font-size: 12px; font-weight: 800; color: #0284c7; text-transform: uppercase; letter-spacing: 0.04em;">🌾 Zasyp (Wytworzono)</div>
                                     <div style="font-size: 24px; font-weight: 800; color: #0369a1; margin-top: 6px;">{suma_zasyp:,} <span style="font-size: 13px; font-weight: 600;">kg</span></div>
                                     {f'''<div style="margin-top: 8px; font-size: 11.5px; font-weight: 800; color: #0284c7; background: #e0f2fe; padding: 4px 10px; border-radius: 6px; display: inline-block;">⚡ Wydajność efektywna: {wyd_efekt_str} <span style="font-weight: 500; font-size: 11px; color: #475569;">(w {zasyp_netto_min} min netto)</span></div>
                                     <div style="margin-top: 4px; font-size: 11.5px; font-weight: 700; color: #0369a1; background: #f0f9ff; border: 1px solid #bae6fd; padding: 3px 8px; border-radius: 6px; display: inline-block;">⏱️ Rzeczywista ({start_str}–{end_str}): {wyd_rzecz_str}</div>''' if suma_zasyp > 0 else ''}
                                </td>
                                <td width="4%">&nbsp;</td>
                                <!-- Workowanie (Spakowano) -->
                                <td width="48%" style="background-color: #f0fdf4; border: 1.5px solid #bbf7d0; border-radius: 12px; padding: 18px; text-align: center;">
                                    <div style="font-size: 12px; font-weight: 800; color: #16a34a; text-transform: uppercase; letter-spacing: 0.04em;">📦 Workowanie (Spakowano)</div>
                                    <div style="font-size: 24px; font-weight: 800; color: #15803d; margin-top: 6px;">{suma_workowanie:,} <span style="font-size: 13px; font-weight: 600;">kg</span></div>
                                </td>
                            </tr>
                        </table>

                        <!-- SECTION 2 & 3: DOWNTIMES (CONDITIONAL) -->
                        {downtime_section_html}

                        <!-- SECTION 4: NOTES (CONDITIONAL) -->
                        {notes_section_html}

                        <!-- ATTACHMENTS LIST -->
                        {att_html}

                    </td>
                </tr>

                <!-- FOOTER -->
                <tr>
                    <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 18px 30px; font-size: 12px; color: #64748b; text-align: center;">
                        Wiadomość wygenerowana automatycznie przez <strong>Raport Produkcyjny AGRO</strong>.<br>
                        Data wysyłki: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}
                    </td>
                </tr>

            </table>

        </body>
        </html>
        """
