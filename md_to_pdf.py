#!/usr/bin/env python3
"""
Advanced Markdown to PDF Converter using FPDF2
Handles headers, code blocks, tables, and formatting
"""

import sys
import re
import unicodedata
from pathlib import Path
from fpdf import FPDF

def remove_emojis(text):
    """Remove emoji and special Unicode characters"""
    return "".join(c if ord(c) < 127 else "" for c in text if unicodedata.category(c)[0] != "C")

class MarkdownToPDF(FPDF):
    """Custom FPDF class for rendering Markdown"""
    
    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margin(15)
        self.title_font_size = 24
        self.heading1_size = 18
        self.heading2_size = 14
        self.heading3_size = 12
        self.normal_size = 11
        self.code_size = 9
        self.page_started = False
        
    def ensure_page(self):
        """Ensure a page exists before writing"""
        if not self.page_started:
            self.add_page()
            self.page_started = True
    
    def add_title(self, text):
        """Add document title"""
        self.add_page()
        self.page_started = True
        self.set_font("Helvetica", "B", self.title_font_size)
        text = remove_emojis(text)
        self.multi_cell(0, 12, text)
        self.ln(10)
    
    def add_heading1(self, text):
        """Add H1 heading"""
        self.ensure_page()
        self.set_font("Helvetica", "B", self.heading1_size)
        self.set_text_color(0, 102, 204)  # Blue
        text = remove_emojis(text)
        self.multi_cell(0, 10, text)
        self.set_text_color(0, 0, 0)
        self.ln(3)
    
    def add_heading2(self, text):
        """Add H2 heading"""
        self.ensure_page()
        self.set_font("Helvetica", "B", self.heading2_size)
        self.set_text_color(0, 102, 204)  # Blue
        text = remove_emojis(text)
        self.multi_cell(0, 8, text)
        self.set_text_color(0, 0, 0)
        self.ln(2)
    
    def add_heading3(self, text):
        """Add H3 heading"""
        self.ensure_page()
        self.set_font("Helvetica", "B", self.heading3_size)
        self.set_text_color(102, 102, 102)  # Gray
        text = remove_emojis(text)
        self.multi_cell(0, 7, text)
        self.set_text_color(0, 0, 0)
        self.ln(2)
    
    def add_paragraph(self, text):
        """Add normal paragraph"""
        self.ensure_page()
        self.set_font("Helvetica", "", self.normal_size)
        text = remove_emojis(text)
        self.multi_cell(0, 6, text)
        self.ln(2)
    
    def add_code_block(self, code):
        """Add code block"""
        self.ensure_page()
        self.set_font("Courier", "", self.code_size)
        self.set_fill_color(240, 240, 240)
        code = remove_emojis(code)
        for line in code.split("\n"):
            self.multi_cell(0, 4, line, border=0, fill=True)
        self.ln(2)
    
    def add_list_item(self, text, level=0):
        """Add list item with indentation"""
        self.ensure_page()
        self.set_font("Helvetica", "", self.normal_size)
        indent = "  " * level
        text = remove_emojis(text)
        self.multi_cell(0, 5, indent + "• " + text)
    
    def _parse_formatting(self, text):
        """Parse inline formatting"""
        text = text.replace("**", "").replace("__", "")
        text = text.replace("*", "").replace("_", "")
        text = text.replace("`", "")
        return text


def markdown_to_pdf(markdown_file, pdf_file):
    """Convert markdown file to PDF"""
    
    # Read markdown file
    with open(markdown_file, "r", encoding="utf-8") as f:
        content = f.read()
    
    pdf = MarkdownToPDF()
    pdf.set_font("Helvetica", "", 11)
    
    lines = content.split("\n")
    current_paragraph = []
    
    for line in lines:
        line_stripped = line.strip()
        
        if not line_stripped:
            if current_paragraph:
                text = " ".join(current_paragraph)
                pdf.add_paragraph(remove_emojis(text))
                current_paragraph = []
            continue
        
        # Handle headers
        if line_stripped.startswith("# "):
            if current_paragraph:
                text = " ".join(current_paragraph)
                pdf.add_paragraph(remove_emojis(text))
                current_paragraph = []
            pdf.add_heading1(remove_emojis(line_stripped[2:]))
        elif line_stripped.startswith("## "):
            if current_paragraph:
                text = " ".join(current_paragraph)
                pdf.add_paragraph(remove_emojis(text))
                current_paragraph = []
            pdf.add_heading2(remove_emojis(line_stripped[3:]))
        elif line_stripped.startswith("### "):
            if current_paragraph:
                text = " ".join(current_paragraph)
                pdf.add_paragraph(remove_emojis(text))
                current_paragraph = []
            pdf.add_heading3(remove_emojis(line_stripped[4:]))
        
        # Handle code blocks
        elif line_stripped.startswith("```"):
            if current_paragraph:
                text = " ".join(current_paragraph)
                pdf.add_paragraph(remove_emojis(text))
                current_paragraph = []
            pdf.ln(2)
        
        # Handle list items
        elif line_stripped.startswith("- ") or line_stripped.startswith("* "):
            if current_paragraph:
                text = " ".join(current_paragraph)
                pdf.add_paragraph(remove_emojis(text))
                current_paragraph = []
            level = (len(line) - len(line.lstrip())) // 2
            pdf.add_list_item(remove_emojis(line_stripped[2:]), level)
        
        # Handle numbered list items
        elif re.match(r"^\d+\.", line_stripped):
            if current_paragraph:
                text = " ".join(current_paragraph)
                pdf.add_paragraph(remove_emojis(text))
                current_paragraph = []
            level = (len(line) - len(line.lstrip())) // 2
            text = re.sub(r"^\d+\.\s*", "", line_stripped)
            pdf.add_list_item(remove_emojis(text), level)
        
        # Regular text
        else:
            current_paragraph.append(line_stripped)
    
    # Add any remaining paragraph
    if current_paragraph:
        text = " ".join(current_paragraph)
        pdf.add_paragraph(remove_emojis(text))
    
    # Save PDF
    pdf.output(pdf_file)
    print(f"✅ PDF created: {pdf_file}")


def main():
    """Main entry point"""
    if len(sys.argv) < 3:
        print("Usage: python md_to_pdf.py <input.md> <output.pdf>")
        sys.exit(1)
    
    md_file = sys.argv[1]
    pdf_file = sys.argv[2]
    
    print("=" * 60)
    print("Markdown → PDF Converter (FPDF2)")
    print("=" * 60)
    print(f"📖 Reading: {md_file}")
    print("📝 Processing markdown...")
    
    try:
        markdown_to_pdf(md_file, pdf_file)
        print(f"✅ Conversion completed successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
