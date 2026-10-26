"""One storage resolver for bug thumbnails, full previews and uploads."""
import json
import os
import re
from pathlib import Path
from flask import current_app, url_for


class BugAttachmentService:
    @staticmethod
    def storage_dir():
        configured = current_app.config.get('BUG_ATTACHMENTS_DIR') or os.getenv('BUG_ATTACHMENTS_DIR')
        return Path(configured) if configured else Path(current_app.static_folder) / 'uploads' / 'bugs'

    @staticmethod
    def resolve(filename):
        if not isinstance(filename, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:png|jpg|jpeg|gif|webp)', filename, re.IGNORECASE):
            return None
        roots = [BugAttachmentService.storage_dir(), Path(current_app.static_folder) / 'uploads' / 'bugs']
        for root in roots:
            root = root.resolve()
            path = (root / filename).resolve()
            if path.is_relative_to(root) and path.is_file():
                return path
        return None

    @staticmethod
    def items(raw):
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError):
                raw = []
        if not isinstance(raw, list):
            return []
        return [dict(filename=name, available=BugAttachmentService.resolve(name) is not None,
                     url=url_for('admin.admin_view_attachment', filename=name))
                for name in raw if isinstance(name, str)]
