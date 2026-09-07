from fpdf import FPDF
import re

def convert_markdown_to_pdf(md_file, output_pdf):
    """
    Convert a Markdown file to PDF without requiring admin rights.
    
    Args:
        md_file: Path to the markdown file
        output_pdf: Path to the output PDF file
    """
    try:
        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()
    except FileNotFoundError:
        print(f"Error: File '{md_file}' not found.")
        return
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    
    lines = md_content.split('\n')
    
    for line in lines:
        if not line.strip():
            pdf.ln(5)
            continue
        
        # Handle headers
        if line.startswith('# '):
            pdf.set_font("Arial", "B", size=16)
            pdf.multi_cell(0, 10, line.replace('# ', ''))
            pdf.set_font("Arial", size=12)
        elif line.startswith('## '):
            pdf.set_font("Arial", "B", size=14)
            pdf.multi_cell(0, 10, line.replace('## ', ''))
            pdf.set_font("Arial", size=12)
        elif line.startswith('### '):
            pdf.set_font("Arial", "B", size=13)
            pdf.multi_cell(0, 10, line.replace('### ', ''))
            pdf.set_font("Arial", size=12)
        # Handle bold and italic
        elif '**' in line or '__' in line or '*' in line or '_' in line:
            text = line.replace('**', '').replace('__', '').replace('*', '').replace('_', '')
            pdf.multi_cell(0, 10, text)
        else:
            pdf.multi_cell(0, 10, line)
    
    try:
        pdf.output(output_pdf)
        print(f"Successfully converted '{md_file}' to '{output_pdf}'")
    except Exception as e:
        print(f"Error saving PDF: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python markdown_to_pdf.py <input.md> <output.pdf>")
        print("Example: python markdown_to_pdf.py README.md README.pdf")
    else:
        convert_markdown_to_pdf(sys.argv[1], sys.argv[2])
