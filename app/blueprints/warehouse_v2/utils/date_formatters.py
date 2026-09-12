import re
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta

def parse_date_obj(d_val):
    """Safely parse a date value from string, date, or datetime object."""
    if not d_val:
        return None
    if isinstance(d_val, (datetime, date)):
        return d_val if isinstance(d_val, date) else d_val.date()
    if isinstance(d_val, str):
        for fmt in ('%Y-%m-%d', '%d.%m.%Y', '%Y/%m/%d', '%Y-%m-%d %H:%M:%S', '%d-%m-%Y'):
            try:
                return datetime.strptime(d_val.strip()[:10], fmt).date()
            except Exception:
                pass
    return None

def compute_expiry_date(exp_val, prod_date_val=None, fmt='%Y-%m-%d'):
    """Compute and format standardized expiry date based on raw date or duration string."""
    if not exp_val:
        return '-'
    if hasattr(exp_val, 'strftime'):
        try:
            return exp_val.strftime(fmt)
        except Exception:
            return str(exp_val)
    exp_str = str(exp_val).strip()
    if not exp_str or exp_str in ('-', 'None', 'null', 'brak'):
        return '-'
    parsed_exp = parse_date_obj(exp_str)
    if parsed_exp and ('-' in exp_str or '.' in exp_str or '/' in exp_str) and len(exp_str) >= 8:
        return parsed_exp.strftime(fmt)
    base_date = parse_date_obj(prod_date_val) or date.today()
    match_months = re.search(r'(\d+)\s*(?:miesi|m-c|m\b|mies)', exp_str, re.IGNORECASE)
    if match_months:
        months = int(match_months.group(1))
        return (base_date + relativedelta(months=months)).strftime(fmt)
    match_days = re.search(r'(\d+)\s*(?:dni|d\b|dzień)', exp_str, re.IGNORECASE)
    if match_days:
        days = int(match_days.group(1))
        return (base_date + timedelta(days=days)).strftime(fmt)
    match_years = re.search(r'(\d+)\s*(?:rok|lat|lata)', exp_str, re.IGNORECASE)
    if match_years:
        years = int(match_years.group(1))
        return (base_date + relativedelta(years=years)).strftime(fmt)
    if exp_str.isdigit():
        months = int(exp_str)
        return (base_date + relativedelta(months=months)).strftime(fmt)
    return exp_str

def format_date_val(val, fmt='%Y-%m-%d'):
    """Format date or datetime object into a target format string."""
    if not val:
        return '-'
    if hasattr(val, 'strftime'):
        try:
            return val.strftime(fmt)
        except Exception:
            return str(val)
    return str(val)
