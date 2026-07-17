"""Test parsowania kodu SUR0000017791467317720"""
import re

# Symulacja nowego regex
SCAN_TOKEN_PATTERN = re.compile(
    r'(R\d{6}|[A-Z]{3}\d{18,20}|SUR-?\d+|OPK-?\d+|DOD-?\d+|PAL-?\d+|MS01|MP01|MDM01|MOP01|MGW01|MGW02|OS\d{2}|OSIP|BB\d{2}|MZ\d{2}(?:-\d{2})?|BF_MS01|BF_MP01|KO\d{2}|PSD01|PSD|RAMPA|MIX01|W_TRANZYCIE_OSIP)',
    re.IGNORECASE,
)

def _normalize_scanned_code(raw_code: str) -> str:
    code = str(raw_code or '').strip().upper()
    if not code:
        return ''

    code = re.sub(r'[\r\n\t]+', ' ', code).strip()

    match = SCAN_TOKEN_PATTERN.search(code)
    if match:
        return match.group(1).upper()

    gs1_ai_match = re.search(r'\(00\)\s*(\d{18})', code)
    if gs1_ai_match:
        return gs1_ai_match.group(1)

    gs1_00_match = re.search(r'\b00(\d{18})\b', code)
    if gs1_00_match:
        return gs1_00_match.group(1)

    digits_18_20_match = re.search(r'\b\d{18,20}\b', code)
    if digits_18_20_match:
        return digits_18_20_match.group(0)

    return code

def _extract_prefixed_id(code: str) -> tuple[str | None, int | None]:
    match = re.match(r'^(SUR|OPK|DOD|PAL)-?(\d+)$', str(code or '').strip().upper())
    if not match:
        return None, None
    prefix = match.group(1)
    digits = match.group(2)
    
    if len(digits) > 10:
        return None, None
        
    return prefix, int(digits)

def _is_sscc_code(code: str) -> bool:
    normalized = str(code or '').strip().upper()
    return bool(re.match(r'^([A-Z]{3}\d{18,20}|\d{18,20}|00\d{18,20})$', normalized))

# Test
test_code = "SUR0000017791467317720"
normalized = _normalize_scanned_code(test_code)
prefixed_type, prefixed_id = _extract_prefixed_id(normalized)
is_sscc = _is_sscc_code(normalized)

print(f"Kod wejściowy: {test_code}")
print(f"Po normalizacji: {normalized}")
print(f"Prefixed type: {prefixed_type}")
print(f"Prefixed ID: {prefixed_id}")
print(f"Is SSCC: {is_sscc}")
print()

if is_sscc:
    print("✅ KOD ZOSTANIE ROZPOZNANY jako SSCC!")
    print(f"   Lookup będzie szukać po nr_palety = '{normalized}'")
else:
    print("❌ KOD NIE ZOSTANIE ROZPOZNANY")

# Test dodatkowych przypadków
print("\n=== Inne testy ===")
test_cases = [
    "SUR-123",           # Standardowy format z myślnikiem
    "SUR123",            # Format bez myślnika (krótki ID)
    "PAL123456789012",   # PAL z długim kodem
    "0000017791467317720",  # Same cyfry (20 cyfr)
]

for tc in test_cases:
    norm = _normalize_scanned_code(tc)
    ptype, pid = _extract_prefixed_id(norm)
    is_sc = _is_sscc_code(norm)
    print(f"{tc:25} → norm={norm:25} prefix={ptype!s:4} id={pid!s:10} sscc={is_sc}")
