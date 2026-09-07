#!/usr/bin/env python3
"""
Batch convert all MQTT documentation to PDF
"""

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent

# List of files to convert individually
MD_FILES = [
    "MQTT_README.md",
    "MQTT_QUICK_REFERENCE.md",
    "MQTT_ARCHITECTURE.md",
    "MQTT_FAQ.md",
    "MQTT_DOCUMENTATION.md",
    "MQTT_INDEX.md",
]

def convert_all():
    """Convert all markdown files to PDF"""
    
    print("=" * 60)
    print("MQTT DOCUMENTATION - BATCH PDF CONVERSION")
    print("=" * 60)
    print()
    
    results = []
    
    for md_file in MD_FILES:
        md_path = REPO_ROOT / md_file
        pdf_file = md_file.replace('.md', '.pdf')
        pdf_path = REPO_ROOT / pdf_file
        
        if not md_path.exists():
            print(f"[SKIP] {md_file} - not found")
            results.append((md_file, False, "File not found"))
            continue
        
        try:
            print(f"[...] Converting {md_file} to {pdf_file}...")
            
            cmd = ["python", "simple_md_to_pdf.py", str(md_path), str(pdf_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and pdf_path.exists():
                size_kb = pdf_path.stat().st_size / 1024
                print(f"[OK ] {pdf_file} ({size_kb:.1f} KB)")
                results.append((md_file, True, size_kb))
            else:
                print(f"[ERR] {md_file} - conversion failed")
                print(f"      Error: {result.stderr[:100]}")
                results.append((md_file, False, result.stderr[:100]))
        
        except subprocess.TimeoutExpired:
            print(f"[ERR] {md_file} - timeout")
            results.append((md_file, False, "Timeout"))
        except Exception as e:
            print(f"[ERR] {md_file} - {e}")
            results.append((md_file, False, str(e)))
    
    # Summary
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    success = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - success
    
    print(f"\nConverted: {success}/{len(results)} files")
    print()
    
    # Check for merged PDF
    merged_pdf = REPO_ROOT / "MQTT_COMPLETE_DOCUMENTATION.pdf"
    if merged_pdf.exists():
        size_mb = merged_pdf.stat().st_size / (1024*1024)
        print(f"[OK ] MQTT_COMPLETE_DOCUMENTATION.pdf ({size_mb:.1f} MB) - MERGED DOCUMENT")
    
    print()
    print("Individual PDFs created:")
    for md_file, ok, info in results:
        if ok:
            pdf_file = md_file.replace('.md', '.pdf')
            print(f"  [✓] {pdf_file} ({info:.1f} KB)")
        else:
            print(f"  [✗] {md_file.replace('.md', '.pdf')} (error: {info})")
    
    print()
    print("=" * 60)
    print(f"All files are in: {REPO_ROOT}")
    print("=" * 60)

if __name__ == "__main__":
    convert_all()
