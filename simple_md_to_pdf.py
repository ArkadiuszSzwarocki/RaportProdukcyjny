#!/usr/bin/env python3
"""
Simple Markdown to PDF Converter - Text-based approach
Fokus na zawartości, nie formatting
"""

import re
from pathlib import Path
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Preformatted
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY

def clean_text(text):
    """Remove emoji and special characters"""
    # Remove emoji
    text = re.sub(r'[\U0001F300-\U0001F9FF]+', '', text)
    # Remove other problematic unicode
    text = ''.join(char for char in text if ord(char) < 128 or char in '\n\r\t')
    return text

def create_pdf(markdown_file, pdf_file):
    """Create PDF from Markdown"""
    
    print(f"[1/3] Reading: {markdown_file}")
    
    with open(markdown_file, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    
    # Create PDF document
    doc = SimpleDocTemplate(pdf_file, pagesize=A4,
                           rightMargin=0.5*inch,
                           leftMargin=0.5*inch,
                           topMargin=0.5*inch,
                           bottomMargin=0.5*inch)
    
    # Create styles
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor='#0066CC',
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    heading1_style = ParagraphStyle(
        'CustomHeading1',
        parent=styles['Heading1'],
        fontSize=16,
        textColor='#0066CC',
        spaceAfter=12,
        spaceBefore=12
    )
    
    heading2_style = ParagraphStyle(
        'CustomHeading2',
        parent=styles['Heading2'],
        fontSize=12,
        textColor='#0066CC',
        spaceAfter=10,
        spaceBefore=10
    )
    
    heading3_style = ParagraphStyle(
        'CustomHeading3',
        parent=styles['Heading3'],
        fontSize=11,
        textColor='#333333',
        spaceAfter=8,
        spaceBefore=8
    )
    
    code_style = ParagraphStyle(
        'Code',
        parent=styles['Normal'],
        fontName='Courier',
        fontSize=8,
        textColor='#333333',
        leftIndent=10,
        rightIndent=10,
        spaceAfter=6,
        backColor='#F0F0F0'
    )
    
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=10,
        alignment=TA_JUSTIFY,
        spaceAfter=10,
        leading=14
    )
    
    # Process content
    print("[2/3] Processing markdown...")
    
    story = []
    lines = content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        i += 1
        
        # Skip empty lines
        if not line.strip():
            story.append(Spacer(1, 0.1*inch))
            continue
        
        # Skip comments
        if line.strip().startswith('<!--'):
            continue
        
        # Page break markers
        if 'PAGE BREAK' in line.upper():
            story.append(PageBreak())
            continue
        
        # Main heading
        if line.startswith('# '):
            text = clean_text(line[2:].strip())
            story.append(Paragraph(text, title_style))
        
        # Heading 1
        elif line.startswith('## '):
            text = clean_text(line[3:].strip())
            story.append(Paragraph(text, heading1_style))
        
        # Heading 2
        elif line.startswith('### '):
            text = clean_text(line[4:].strip())
            story.append(Paragraph(text, heading2_style))
        
        # Heading 3
        elif line.startswith('#### '):
            text = clean_text(line[5:].strip())
            story.append(Paragraph(text, heading3_style))
        
        # Code block
        elif line.strip().startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            
            code_text = '\n'.join(code_lines[:50])  # Limit to 50 lines
            if len(code_lines) > 50:
                code_text += f"\n... ({len(code_lines) - 50} more lines) ..."
            
            code_text = clean_text(code_text)
            
            # Split long code blocks
            for chunk in code_text.split('\n'):
                if chunk:
                    story.append(Preformatted(chunk, code_style))
            
            story.append(Spacer(1, 0.1*inch))
        
        # Regular text
        else:
            text = clean_text(line.strip())
            if text:
                # Simple list detection
                if text.startswith(('- ', '* ', '+ ')):
                    text = '  • ' + text[2:]
                elif re.match(r'^\d+\.\s', text):
                    text = '  ' + text
                
                story.append(Paragraph(text, body_style))
    
    # Build PDF
    print("[3/3] Creating PDF...")
    doc.build(story)
    
    file_size = Path(pdf_file).stat().st_size
    print(f"\nSuccess! PDF created: {pdf_file}")
    print(f"Size: {file_size / (1024*1024):.1f} MB")
    
    return True

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python simple_md_to_pdf.py <input.md> [output.pdf]")
        sys.exit(1)
    
    md_file = sys.argv[1]
    pdf_file = sys.argv[2] if len(sys.argv) > 2 else md_file.replace('.md', '.pdf')
    
    print("=" * 60)
    print("Markdown to PDF - ReportLab")
    print("=" * 60)
    print()
    
    if not Path(md_file).exists():
        print(f"Error: File not found: {md_file}")
        sys.exit(1)
    
    try:
        create_pdf(md_file, pdf_file)
        print("\n" + "=" * 60)
        print("DONE!")
        print("=" * 60)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
