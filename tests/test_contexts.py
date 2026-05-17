"""Tests for template context processors."""

from app.core.contexts import inject_role_permissions


def test_master_admin_alias_has_master_access(app):
    """Role variant 'master admin' should be treated as masteradmin."""
    with app.test_request_context('/'):
        from flask import session

        session['rola'] = 'master admin'
        context = inject_role_permissions()
        assert context['has_master_access'] is True
        assert context['has_admin_access'] is True


def test_master_admin_alias_has_full_role_access(app):
    """Master admin alias should bypass RBAC checks."""
    with app.test_request_context('/'):
        from flask import session

        session['rola'] = 'master_admin'
        context = inject_role_permissions()
        assert context['role_has_access']('logs') is True

