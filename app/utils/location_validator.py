"""
Walidacja lokalizacji magazynowych.

Zapobiega używaniu kodów zbiorników produkcyjnych (BB*, MZ*, KO*) 
jako lokalizacji w magazynie surowców, opakowań i wyrobów gotowych.
"""
import re

# Wzorce kodów zbiorników produkcyjnych (NIE mogą być lokalizacjami magazynowymi!)
PRODUCTION_TANK_PATTERNS = [
    r'^BB\d{1,2}$',      # BB01, BB02, ..., BB24
    r'^MZ\d{1,2}$',      # MZ01, MZ02, ..., MZ24
    r'^MZ\d{2}-\d{2}$',  # MZ05-01, MZ06-01
    r'^KO\d{1,2}$',      # KO01, KO02, ..., KO24
    r'^CZ\d{1,2}$',      # CZ01, CZ02, ... (Czyszczenie)
]

def is_production_tank_code(location_code):
    """
    Sprawdza czy podany kod to kod zbiornika produkcyjnego.
    
    Args:
        location_code: Kod lokalizacji do sprawdzenia
        
    Returns:
        True jeśli to kod zbiornika produkcyjnego (BB*, MZ*, KO*)
        False w przeciwnym wypadku
    """
    if not location_code:
        return False
    
    normalized = str(location_code).strip().upper()
    if not normalized:
        return False
        
    for pattern in PRODUCTION_TANK_PATTERNS:
        if re.match(pattern, normalized):
            return True
    return False


def validate_warehouse_location(location_code, allow_empty=True):
    """
    Waliduje czy kod lokalizacji może być użyty w magazynie.
    
    Args:
        location_code: Kod lokalizacji do sprawdzenia
        allow_empty: Czy dozwolone są puste/None wartości
        
    Returns:
        Tuple (is_valid: bool, error_message: str)
        
    Examples:
        >>> validate_warehouse_location("R021002")
        (True, None)
        
        >>> validate_warehouse_location("BB15")
        (False, "BB15 to kod zbiornika produkcyjnego. Użyj kodów regałów (np. R021002)")
        
        >>> validate_warehouse_location(None, allow_empty=True)
        (True, None)
        
        >>> validate_warehouse_location(None, allow_empty=False)
        (False, "Lokalizacja jest wymagana")
    """
    if not location_code or str(location_code).strip() == '':
        if allow_empty:
            return True, None
        else:
            return False, "Lokalizacja jest wymagana"
    
    normalized = str(location_code).strip().upper()
    
    if is_production_tank_code(normalized):
        return False, (
            f"{normalized} to kod zbiornika produkcyjnego (BB/MZ/KO są tylko do przypisywania surowców w produkcji). "
            "Użyj kodów regałów magazynowych (np. R021002, R030601)"
        )
    
    return True, None


def normalize_warehouse_location(location_code):
    """
    Normalizuje kod lokalizacji magazynowej (uppercase, trim).
    
    Args:
        location_code: Kod lokalizacji do znormalizowania
        
    Returns:
        Znormalizowany kod lub None jeśli pusta wartość
    """
    if not location_code:
        return None
    
    normalized = str(location_code).strip().upper()
    return normalized if normalized else None
