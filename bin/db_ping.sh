#!/bin/bash
# DB_PING - Проверка соединения с БД (read-only тест)
# Использование: bin/db_ping.sh

set -euo pipefail

SCRIPT_DIR="$(dirname "$0")"
source "$SCRIPT_DIR/db_env.sh"

# Read-only тест соединения
echo "Проверка соединения с БД..."

RESULT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -c "
SELECT current_user || '@' || current_database();
" 2>&1)

if [ $? -eq 0 ]; then
    echo "✅ Успешное подключение: $RESULT"
    exit 0
else
    echo "❌ Ошибка подключения:"
    echo "$RESULT"
    exit 1
fi
