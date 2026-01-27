from typing import Callable, Any

class ValidationError(Exception):
    pass


def require_field(form: Any, key: str, *, cast: Callable[[str], Any] | None = None, allow_empty: bool = False) -> Any:
    """
    Extract `key` from `form` (e.g. `request.form`) and validate presence.
    - If missing or empty (and allow_empty is False) raises ValidationError.
    - If `cast` provided, attempts to cast value and raises ValidationError on failure.
    Returns the (optionally cast) value.
    """
    if form is None:
        raise ValidationError(f"Missing form data for '{key}'")
    val = form.get(key)
    if val is None:
        raise ValidationError(f"Missing required field: {key}")
    if not allow_empty and isinstance(val, str) and val.strip() == '':
        raise ValidationError(f"Field '{key}' cannot be empty")
    if cast:
        try:
            return cast(val)
        except Exception as e:
            raise ValidationError(f"Field '{key}' invalid: {e}")
    return val


def optional_field(form: Any, key: str, *, default: Any = None, cast: Callable[[str], Any] | None = None) -> Any:
    """
    Extract optional field with default and optional casting.
    """
    if form is None:
        return default
    val = form.get(key, default)
    if val is default:
        return default
    if cast:
        try:
            return cast(val)
        except Exception:
            return default
    return val
