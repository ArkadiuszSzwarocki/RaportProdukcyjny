"""Compatibility facade for legacy ``app.db`` imports.

New code should import directly from ``app.core.database`` or a repository.
The facade remains temporarily because many routes still use named imports, but
it no longer performs wildcard imports or emits a warning for every process.
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
_MODULES = tuple(import_module(name) for name in _MODULE_NAMES)


def __getattr__(name):
    for module in _MODULES:
        if hasattr(module, name):
            return getattr(module, name)
    raise AttributeError(f"module 'app.db' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))


__all__ = sorted({
    name
    for module in _MODULES
    for name in vars(module)
    if not name.startswith('_')
})
