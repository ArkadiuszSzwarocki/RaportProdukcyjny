"""Shared daily summaries for Excel and PDF, using archived samples only."""
from scripts.reports.text_utils import polskie_znaki_pdf


def summary_rows(measurements):
    rows = []
    for device in measurements:
        for key, label, unit in [('temperature', 'Temperatura', '°C'), ('humidity', 'Wilgotność', '%')]:
            values = device['summary'].get(key)
            rows.append({'Czujnik': device['name'], 'Doba': device['day'], 'Pomiar': label,
                         'Jednostka': unit, 'Minimum': values['min'] if values else None,
                         'Maksimum': values['max'] if values else None,
                         'Średnia odczytów': values['mean'] if values else None,
                         'Liczba odczytów': values['count'] if values else 0,
                         'Pierwszy odczyt': device.get('first', ''), 'Ostatni odczyt': device.get('last', ''),
                         'Przerwy ponad 15 min': device.get('gaps', 0),
                         'Uwagi': 'Średnia z dostępnych odczytów; czas Europe/Warsaw' if values else 'Brak pomiarów w tej dobie'})
    return rows


def write_excel(writer, measurements):
    import pandas as pd
    pd.DataFrame(summary_rows(measurements)).to_excel(writer, sheet_name='Pomiary - Podsumowanie', index=False)
    samples = [{'Czujnik': device['name'], 'Czas Europe/Warsaw': row['time'],
                'Temperatura °C': row['temperature'], 'Wilgotność %': row['humidity']}
               for device in measurements for row in device['samples']]
    pd.DataFrame(samples, columns=['Czujnik', 'Czas Europe/Warsaw', 'Temperatura °C', 'Wilgotność %']).to_excel(
        writer, sheet_name='Pomiary - Odczyty', index=False)


def render_pdf(pdf, measurements):
    if not measurements:
        return
    pdf.ln(4)
    pdf.set_font('Arial', 'B', 10)
    pdf.set_fill_color(226, 232, 240)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 7, txt=polskie_znaki_pdf('POMIARY DOBOWE - iPomiar'), ln=1, fill=True)
    pdf.set_font('Arial', size=9)
    pdf.multi_cell(0, 5, txt=polskie_znaki_pdf('Czas: Europe/Warsaw. Średnie z dostępnych odczytów, bez uzupełniania braków.'))
    for device in measurements:
        pdf.set_font('Arial', 'B', 9)
        pdf.cell(0, 6, txt=polskie_znaki_pdf(device['name'][:100] + ' | ' + device['day']), ln=1)
        pdf.set_font('Arial', size=9)
        if not device['latest']:
            pdf.cell(0, 5, txt=polskie_znaki_pdf('Brak pomiarów w tej dobie'), ln=1)
            continue
        pdf.cell(0, 5, txt=polskie_znaki_pdf(f'Odczyty: {device["first"]} - {device["last"]}'), ln=1)
        for row in summary_rows([device]):
            if row['Liczba odczytów']:
                text = (f'{row["Pomiar"]}: min {row["Minimum"]:.1f}, maks {row["Maksimum"]:.1f}, '
                        f'średnia {row["Średnia odczytów"]:.1f} {row["Jednostka"]}; odczytów: {row["Liczba odczytów"]}')
                pdf.cell(0, 5, txt=polskie_znaki_pdf(text), ln=1)
        if device.get('gaps'):
            pdf.cell(0, 5, txt=polskie_znaki_pdf(f'Przerwy między odczytami ponad 15 minut: {device["gaps"]}'), ln=1)
