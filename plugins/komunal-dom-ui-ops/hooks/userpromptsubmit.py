#!/usr/bin/env python3
import json, sys
raw = sys.stdin.read()
try:
 data = json.loads(raw or '{}')
except Exception:
 sys.exit(0)
text = json.dumps(data, ensure_ascii=False).lower()
if any(x in text for x in ['форма', 'django admin', 'change_form', 'кнопк', 'fieldsets', 'таблиц', 'миграц']):
 print('[komunal-dom-ui-ops] Напоминание: сначала определи render stack (ModelAdmin/template/CSS), затем сделай screenshot-backed verification.', file=sys.stderr)
