#!/usr/bin/env python3
"""Download Material Icons font - better implementation."""

import urllib.request
import os
import sys

fonts_dir = os.path.join('static', 'fonts')
os.makedirs(fonts_dir, exist_ok=True)

output_path = os.path.join(fonts_dir, 'MaterialIcons-Regular.woff2')

# Better URL that returns the actual binary font file
urls = [
    'https://unpkg.com/material-design-icons@7.0.0/iconfont/MaterialIcons-Regular.woff2',
    'https://fonts.gstatic.com/s/materialicons/v140/flUhRq6tzZsQE1IjCFQYfcL-Io1LQA.woff2',
]

print("Downloading Material Icons font...\n")

for url in urls:
    try:
        print(f"Trying: {url[:70]}...")
        
        # Download with proper headers
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')]
        response = opener.open(url, timeout=10)
        
        with open(output_path, 'wb') as f:
            f.write(response.read())
        
        size = os.path.getsize(output_path)
        print(f"✓ Downloaded successfully!")
        print(f"  Location: {output_path}")
        print(f"  Size: {size:,} bytes")
        
        # Verify it's a binary WOFF2 file (should start with wOF2)
        with open(output_path, 'rb') as f:
            header = f.read(4)
            if header == b'wOF2':
                print(f"✓ Valid WOFF2 format confirmed")
                sys.exit(0)
            else:
                print(f"⚠ Warning: File header not recognized: {header[:4]}")
                print(f"  Trying next URL...")
                continue
                
    except Exception as e:
        print(f"✗ Failed: {e}\n")
        continue

print("\n✗ Could not download from any source")
print("\nFallback: Creating empty placeholder file...")
with open(output_path, 'wb') as f:
    f.write(b'')
print(f"  Created: {output_path}")

