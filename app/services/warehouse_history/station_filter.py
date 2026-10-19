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
