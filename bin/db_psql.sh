#!/bin/bash
# DB_PSQL - Интерактивный psql с безопасными credential'ами
# Использование: bin/db_psql.sh
# Использование: bin/db_psql.sh -c "SELECT 1;"

set -euo pipefail

SCRIPT_DIR="$(dirname "$0)"
source "$SCRIPT_DIR/db_env.sh"

# Проверяем ping
if ! "$SCRIPT_DIR/db_ping.sh" > /dev/null 2>&1; then
    echo "ОШИБКА: Нет доступа к БД. Выполните bin/db_ping.sh для диагностики" >&2
    exit 1
fi

# Открываем интерактивный psql
echo "Подключение к $DB_NAME@$DB_HOST как $DB_USER..."
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" "$@"
