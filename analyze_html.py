with open('dashboard_html.txt', 'r', encoding='utf-8') as f:
    content = f.read()

import re

# Check for row-zaplanowane
print("Searching for 'row-zaplanowane'...")
rows = list(re.finditer(r'<tr class="row-zaplanowane">', content))
print(f"Found {len(rows)} zaplanowane rows")

if rows:
    # Get context for first row
    for i, match in enumerate(rows[:1]):
        start = max(0, match.start())
        end = min(len(content), match.start() + 1500)
        print(f"\n--- Row {i+1} content ---")
        print(content[start:end][:1000])  # Print first 1000 chars
        
        # Check what's in this row
        row_section = content[match.start():end]
        if 'Wznów' in row_section:
            print("✓ Found 'Wznów' button in this row")
        else:
            print("✗ No 'Wznów' button")
            
        if 'przywroc_zlecenie' in row_section:
            print("✓ Found 'przywroc_zlecenie' in this row")
        else:
            print("✗ No 'przywroc_zlecenie' form")
            
        # Check for START button
        if 'btn-start' in row_section:
            print("✓ Found 'START' button")
        else:
            print("✗ No START button")
