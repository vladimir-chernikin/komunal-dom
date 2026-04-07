#!/usr/bin/env bash
set -euo pipefail
cd /var/www/komunal-dom_ru
printf '== Marketplaces ==\n'
claude plugin marketplace list || true
printf '\n== Installed Plugins ==\n'
python3 - <<'PY'
from pathlib import Path
import json
p = Path('/root/.claude/plugins/installed_plugins.json')
obj = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
for name, versions in obj.get('plugins', {}).items():
    print(name)
    for item in versions:
        print('  scope=', item.get('scope'), 'path=', item.get('installPath'))
PY
printf '\n== MCP ==\n'
claude mcp list || true
printf '\n== Project Rules ==\n'
ls -1 .claude/hookify.*.local.md 2>/dev/null || true
printf '\n== Project Launcher Smoke ==\n'
printf 'List only the project plugins and MCP in this session.\n' | ./bin/claude-project.sh -p --permission-mode dontAsk --allowedTools Read,Bash
