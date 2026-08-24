"""Auth management module."""
from flask import Blueprint
from .base import auth_bp
from . import user_profile

__all__ = ['auth_bp']

