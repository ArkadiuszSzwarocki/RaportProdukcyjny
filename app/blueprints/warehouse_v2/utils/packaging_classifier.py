def classify_packaging_type(product_name: str, type_str: str, amount: float = 0, unit: str = 'kg', raw_pkg: str = '') -> str:
    """Classify physical pallet packaging type (Big Bag, Worek 25kg, Karton, Rolka, etc.)."""
    p_name = str(product_name or '').upper()
    t_str = str(type_str or '').upper()
    pkg_raw = str(raw_pkg or '').upper()
    
    # PRIORITIZE raw_packaging_type (typ_opakowania) - if it's set to Taśma or Karton, use it
    if pkg_raw == 'TAŚMA' or pkg_raw == 'TASMA':
        return 'Taśma (taśma do pakowania)'
    if pkg_raw == 'KARTON':
        return 'Karton (opakowanie zbiorcze)'
    
    # Otherwise, classify by product name and other hints
    if 'BIG' in pkg_raw or 'BB' in pkg_raw or 'BIG BAG' in p_name or 'BIGBAG' in p_name or ' BB' in p_name or '1000KG' in p_name or '1000 KG' in p_name or 'WAPNO BB' in p_name:
        return 'Big Bag (1000kg)'
    if '25KG' in p_name or '25 KG' in p_name or 'WOREK' in pkg_raw or 'WORKI' in pkg_raw or 'WOREK' in p_name or 'WORK' in p_name:
        return 'Worek (25kg)'
    if '50KG' in p_name or '50 KG' in p_name:
        return 'Worek (50kg)'
    if '20KG' in p_name or '20 KG' in p_name:
        return 'Worek (20kg)'
    if 'KARTON' in pkg_raw or 'KARTON' in p_name:
        return 'Karton'
    if 'FOLIA' in p_name or 'ROLKA' in pkg_raw or 'ROLKA' in p_name or 'KALKA' in p_name:
        return 'Rolka / Folia'
    if 'WIADRO' in p_name or 'WIADRA' in p_name:
        return 'Wiadro'
    if 'KANISTER' in p_name or 'BECZKA' in p_name:
        return 'Kanister / Beczka'
    if t_str == 'OPAKOWANIE':
        return 'Opakowanie / Karton'
    if t_str in ('WYRÓB GOTOWY', 'SUROWIEC', 'DODATEK'):
        if amount and amount >= 800 and ('BB' in p_name or ('SUROWIEC' in t_str and amount % 25 != 0)):
            return 'Big Bag (1000kg)'
        return 'Worek (25kg)'
    return 'Worek (25kg)'
