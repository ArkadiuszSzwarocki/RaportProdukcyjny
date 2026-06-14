import fitz
from PIL import Image

def test_fitz():
    doc = fitz.open() # Create empty pdf
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 50), "Test PDF for PyMuPDF", fontsize=20)
    doc.save("test.pdf")
    doc.close()
    
    # reopen
    doc = fitz.open("test.pdf")
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0))
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img.save("test_rendered.png")
    print("Success. Saved test_rendered.png")

if __name__ == '__main__':
    test_fitz()
