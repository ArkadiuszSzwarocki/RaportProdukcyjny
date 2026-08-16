import os
import re

source = r'a:\GitHub\RaportProdukcyjny\app\services\planning\buffer.py'
with open(source, 'r', encoding='utf-8') as f:
    content = f.read()

# We'll split the file based on the methods.
# Actually, I can just create the files from strings because I have the contents downloaded previously.
