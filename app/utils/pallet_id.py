import time
from datetime import datetime

def generate_pallet_id(linia, type='wyrób gotowy', record_id=None):
    # Prefix
    type = type.lower()
    if type == 'surowiec':
        prefix = 'SUR'
    elif type == 'opakowanie':
        prefix = 'OPK'
    else:
        prefix = 'PSD' if linia.upper() == 'PSD' else 'AGR'
    
    # Date part: DDMMYYYY
    date_str = datetime.now().strftime('%d%m%Y')
    
    # Milliseconds since 1970
    timestamp_ms = int(time.time() * 1000)
    unique_base = timestamp_ms + (record_id or 0)
    ms_part = str(unique_base)[-10:].zfill(10)
    
    return f"{prefix}{date_str}{ms_part}"
