"""Compatibility facade for legacy ``app.db`` named imports.

New code should import directly from ``app.core.database`` or the relevant
repository.  This facade intentionally performs no wildcard/eager imports so
loading ``app.db`` cannot pull every repository into the import graph and
create circular-import side effects.
"""

from importlib import import_module


_MODULE_NAMES = (
    'app.core.database',
    'app.core.database_setup',
    'app.repositories.production_repository',
    'app.repositories.notification_repository',
    'app.repositories.session_repository',
    'app.repositories.push_repository',
)


def __getattr__(name):
    """Resolve a legacy attribute on first use and cache the result."""
    for module_name in _MODULE_NAMES:
        module = import_module(module_name)
        try:
            value = getattr(module, name)
        except AttributeError:
            continue
        globals()[name] = value
        return value
    raise AttributeError(f"module 'app.db' has no attribute {name!r}")


def __dir__():
    """Expose available legacy names for interactive diagnostics only."""
    names = set(globals())
    for module_name in _MODULE_NAMES:
        try:
            module = import_module(module_name)
            names.update(name for name in vars(module) if not name.startswith('_'))
        except Exception:
            # ``dir(app.db)`` must never break application startup diagnostics.
            continue
    return sorted(names)
