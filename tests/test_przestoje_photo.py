import pytest
import os
from unittest.mock import MagicMock
from flask import Flask
from app.blueprints.production.przestoje import _save_przestoj_photo

def test_save_przestoj_photo_empty():
    app = Flask(__name__, root_path=os.path.abspath('.'))
    with app.app_context():
        req = MagicMock()
        req.files = {}
        req.form = {}
        result = _save_przestoj_photo(req)
        assert result is None

def test_save_przestoj_photo_remove():
    app = Flask(__name__, root_path=os.path.abspath('.'))
    with app.app_context():
        req = MagicMock()
        req.files = {}
        req.form = {'remove_zdjecie': '1'}
        result = _save_przestoj_photo(req)
        assert result == ''
