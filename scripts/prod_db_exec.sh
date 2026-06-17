#!/bin/bash
# Project wrapper для prod DB access
# Тонкий wrapper, который вызывает глобальный reusable wrapper
# Использование: scripts/prod_db_exec.sh <command> [arguments]

exec /root/.claude/bin/komunal_dom_db.sh "$@"
