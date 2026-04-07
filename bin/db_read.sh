#!/bin/bash
# DB_READ - Выполнение read-only SQL запросов
# Использование: bin/db_read.sh "SELECT * FROM services_catalog LIMIT 5;"
# Использование: bin/db_read.sh -f query.sql

set -euo pipefail

SCRIPT_DIR="$(dirname "$0")"
source "$SCRIPT_DIR/db_env.sh"

# Проверяем ping
if ! "$SCRIPT_DIR/db_ping.sh" > /dev/null 2>&1; then
    echo "ERROR: No DB access. Run bin/db_ping.sh for diagnostics" >&2
    exit 1
fi

# Проверяем аргументы
if [ $# -eq 0 ]; then
    echo "Usage: $0 'SQL_QUERY'" >&2
    echo "Or: $0 -f file.sql" >&2
    exit 1
fi

# Выполняем запрос
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "$*"
