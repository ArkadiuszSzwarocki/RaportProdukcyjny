import re

SCAN_TOKEN_PATTERN = re.compile(
    r'(R\d{6}|[A-Z]{3}\d{18,20}|SUR-?\d+|OPK-?\d+|DOD-?\d+|PAL-?\d+|MS01|MP01|MDM01|MOP01|MGW01|MGW02|OS\d{2}|OSIP|BB\d{2}|MZ\d{2}(?:-\d{2})?|BF_?MS01|BF_?MP01|BFOS|KO\d{2}|PSD01|PSD|RAMPA|MIX01|W_TRANZYCIE_OSIP)',
    re.IGNORECASE,
)


class ScannerCodeNormalizer:
    """Methods for normalizing barcodes, extracting IDs and identifying SSCCs."""

    SCAN_TOKEN_PATTERN = SCAN_TOKEN_PATTERN

    @staticmethod
    def normalize_scanned_code(raw_code: str) -> str:
        """Oczyszcza i normalizuje surowy ciąg ze skanera kodów (w tym JSON i kody GS1)."""
        if not raw_code:
            return ''
            
        raw_str = str(raw_code).strip()
        if ('{' in raw_str and '}' in raw_str) or ('"sscc"' in raw_str):
            try:
                import json
                j_match = re.search(r'\{[\s\S]*\}', raw_str)
                if j_match:
                    parsed = json.loads(j_match.group(0))
                    val = parsed.get('sscc') or parsed.get('nr_palety') or parsed.get('id')
                    if val:
                        raw_str = str(val)
                else:
                    sscc_m = re.search(r'"sscc"\s*:\s*"([^"]+)"', raw_str, re.IGNORECASE)
                    if sscc_m:
                        raw_str = sscc_m.group(1)
            except Exception:
                pass

        code = raw_str.strip().upper()
        if not code:
            return ''

        code = re.sub(r'[\r\n\t]+', ' ', code).strip()

        gs1_ai_match = re.search(r'\(00\)\s*(\d{18})', code)
        if gs1_ai_match:
            return gs1_ai_match.group(1)

        gs1_00_match = re.search(r'\b00(\d{18})\b', code)
        if gs1_00_match:
            return gs1_00_match.group(1)

        digits_18_20_match = re.search(r'\b\d{18,20}\b', code)
        if digits_18_20_match:
            return digits_18_20_match.group(0)

        match = SCAN_TOKEN_PATTERN.search(code)
        if match:
            return match.group(1).upper()

        return code

    @staticmethod
    def extract_prefixed_id(code: str) -> tuple[str | None, int | None]:
        """Wyodrębnia prefix i identyfikator numeryczny (np. SUR-123, OPK456)."""
        match = re.match(r'^(SUR|OPK|DOD|PAL)-?(\d+)$', str(code or '').strip().upper())
        if not match:
            return None, None
        prefix = match.group(1)
        digits = match.group(2)
        if len(digits) > 10:
            return None, None
        return prefix, int(digits)

    @staticmethod
    def is_sscc_code(code: str) -> bool:
        """Weryfikuje, czy kod spełnia standard SSCC lub unikalny numer palety."""
        normalized = str(code or '').strip().upper()
        return bool(re.match(r'^([A-Z]{3}\d{18,20}|\d{18,20}|00\d{18,20})$', normalized))


# Backward compatibility module functions
normalize_scanned_code = ScannerCodeNormalizer.normalize_scanned_code
extract_prefixed_id = ScannerCodeNormalizer.extract_prefixed_id
is_sscc_code = ScannerCodeNormalizer.is_sscc_code
