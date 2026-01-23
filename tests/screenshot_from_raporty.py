import fitz, os, sys

pdf_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'raporty', 'Raport_2026-01-23_new.pdf'))
out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'Raport_2026-01-23_raporty_page1.png'))

if not os.path.exists(pdf_path):
    print('PDF not found:', pdf_path)
    sys.exit(2)

try:
    doc = fitz.open(pdf_path)
    page = doc.load_page(0)
    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat)
    pix.save(out_path)
    print('Saved screenshot to', out_path)
except Exception as e:
    print('Error:', e)
    sys.exit(1)
