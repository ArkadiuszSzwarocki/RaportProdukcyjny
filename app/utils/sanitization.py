"""Sanitization utilities for user-submitted text inputs.
Prevents XSS and HTML injection by stripping or escaping unsafe tags.
"""

import re
from typing import Optional


def sanitize_plain_text(text: Optional[str]) -> str:
    """Sanitize user input by removing HTML tags and script elements.
    
    Args:
        text: Raw user-provided string
        
    Returns:
        Sanitized plain text string
    """
    if not text or not isinstance(text, str):
        return ""

    # Remove script and style elements completely
    cleaned = re.sub(r'<(script|style).*?>.*?</\1>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove remaining HTML tags
    cleaned = re.sub(r'<[^<]+?>', '', cleaned)
    return cleaned.strip()
