"""Exact station/location codes shared by SQL and final history filtering."""
import re


def station_search_pattern(station):
    code = str(station or '').strip().upper()
    if not code:
        return None
    return r'(^|[^A-Z0-9_])' + re.escape(code) + r'($|[^A-Z0-9_])'


def matches_station(item, pattern):
    return any(
        re.search(pattern, str(item.get(field) or '').upper())
        for field in ('stacja', 'skad', 'dokad')
    )


def normalize_station_filters(material, station):
    """A complete station code in the general search is a location filter."""
    material = str(material or '').strip()
    station = str(station or '').strip().upper()
    if not station:
        match = re.fullmatch(r'(BB|MZ|WZ|KO|ZB|MIX|LP|MGW|MS|MP)\s*(\d{1,3})', material, re.IGNORECASE)
        if match:
            return None, (match.group(1) + match.group(2)).upper()
    return material or None, station or None
