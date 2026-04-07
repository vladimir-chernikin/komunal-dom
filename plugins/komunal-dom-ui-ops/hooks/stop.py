#!/usr/bin/env python3
import json
import sys

raw = sys.stdin.read()
try:
    data = json.loads(raw or '{}')
except Exception:
    sys.exit(0)

text = json.dumps(data, ensure_ascii=False).lower()
ui_markers = ['форма', 'button', 'change_form', 'admin.py', 'templates/admin']
if any(marker in text for marker in ui_markers):
    if 'screenshot' not in text and 'playwright' not in text:
        print('[komunal-dom-ui-ops] Stop check: for UI tasks include screenshot or browser verification artifacts.', file=sys.stderr)
