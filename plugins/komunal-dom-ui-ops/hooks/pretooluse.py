#!/usr/bin/env python3
import json, sys
raw = sys.stdin.read()
try:
 data = json.loads(raw or '{}')
except Exception:
 sys.exit(0)
text = json.dumps(data, ensure_ascii=False).lower()
ui_markers = ['admin.py', 'change_form', 'templates/admin', 'static/css/admin_custom.css', '.html']
schema_markers = ['models.py', 'migrations', 'runsql', 'alter table', 'create table', 'drop table']
if any(x in text for x in ui_markers):
 print('[komunal-dom-ui-ops] UI edit detected: verify global admin overrides and Jazzmin interactions before patching.', file=sys.stderr)
if any(x in text for x in schema_markers):
 print('[komunal-dom-ui-ops] Schema-sensitive edit detected: trace RunSQL/raw SQL usage before modifying tables.', file=sys.stderr)
