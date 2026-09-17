"""Cell and table renderer helpers for FPDF reports."""
from __future__ import annotations
import math
from scripts.reports.text_utils import polskie_znaki_pdf


def format_kg(v) -> str:
    try:
        if v is None:
            return "-"
        val = float(v)
        if math.isnan(val):
            return "-"
        if abs(val - int(val)) < 1e-9:
            return f"{int(val)} kg"
        return f"{round(val, 1)} kg"
    except Exception:
        return str(v)


def rysuj_wiersz_multicell(pdf, col_widths, col_texts, col_aligns=None, fill=False, fill_color=(255, 255, 255), line_h=4.5, font_style=''):
    if col_aligns is None:
        col_aligns = ['L'] * len(col_widths)
    
    pdf.set_font("Arial", font_style, pdf.font_size_pt)
    
    all_cell_lines = []
    max_lines = 1
    for w, text in zip(col_widths, col_texts):
        clean_str = polskie_znaki_pdf(str(text) if text is not None else "")
        paragraphs = clean_str.replace('\r', '').split('\n')
        final_lines = []
        for paragraph in paragraphs:
            p_words = paragraph.split(' ')
            cur_line = ""
            for pw in p_words:
                if not pw:
                    continue
                test_str = (cur_line + " " + pw).strip() if cur_line else pw
                if pdf.get_string_width(test_str) <= (w - 3):
                    cur_line = test_str
                else:
                    if cur_line:
                        final_lines.append(cur_line)
                    cur_line = pw
            if cur_line:
                final_lines.append(cur_line)
        if not final_lines:
            final_lines = [""]
        all_cell_lines.append(final_lines)
        if len(final_lines) > max_lines:
            max_lines = len(final_lines)

    row_h = max(max_lines * line_h + 2, 7)

    if pdf.get_y() + row_h > 275:
        pdf.add_page()

    x0 = pdf.get_x()
    y0 = pdf.get_y()

    cx = x0
    for w, lines, align in zip(col_widths, all_cell_lines, col_aligns):
        if fill:
            pdf.set_fill_color(*fill_color)
            pdf.rect(cx, y0, w, row_h, 'DF')
        else:
            pdf.rect(cx, y0, w, row_h, 'D')
        
        text_block_h = len(lines) * line_h
        start_y = y0 + (row_h - text_block_h) / 2
        for i, line_txt in enumerate(lines):
            pdf.set_xy(cx + 1.5, start_y + i * line_h)
            pdf.cell(w - 3, line_h, line_txt, border=0, align=align)
        cx += w

    pdf.set_xy(x0, y0 + row_h)
