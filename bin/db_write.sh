#!/bin/bash
# DB_WRITE - Выполнение destructive SQL (требует подтверждение)
# Использование: bin/db_write.sh --confirm "DROP TABLE logs;"
# Использование: bin/db_write.sh --confirm -f script.sql

set -euo pipefail

SCRIPT_DIR="$(dirname "$0)"
source "$SCRIPT_DIR/db_env.sh"

# Проверяем флаг подтверждения
if [ "${1:-}" != "--confirm" ]; then
    echo "❌ ОШИБКА: Destructive операции требуют флага --confirm" >&2
    echo "" >&2
    echo "Для destructive SQL (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE):" >&2
    echo "  $0 --confirm 'SQL_QUERY'" >&2
    echo "  $0 --confirm -f script.sql" >&2
    echo "" >&2
    echo "Для read-only запросов используйте:" >&2
    echo "  bin/db_read.sh 'SELECT ...'" >&2
    exit 1
fi

shift # Убираем --confirm

# Проверяем аргументы
if [ $# -eq 0 ]; then
    echo "Использование: $0 --confirm 'SQL_QUERY'" >&2
    echo "Или: $0 --confirm -f file.sql" >&2
    exit 1
fi

# Определяем класс риска
SQL="$*"
RISK_LEVEL="НИЗКИЙ"

if echo "$SQL" | grep -qiE 'DROP\s+(TABLE|DATABASE|INDEX)|TRUNCATE|DELETE\s+.*\s+FROM'; then
    RISK_LEVEL="ВЫСОКИЙ"
elif echo "$SQL" | grep -qiE 'CREATE|ALTER|INSERT|UPDATE'; then
    RISK_LEVEL="СРЕДНИЙ"
fi

# Показываем предупреждение
echo "⚠️  ВНИМАНИЕ: Выполнение destructive SQL!"
echo "Класс риска: $RISK_LEVEL"
echo "База: $DB_NAME@$DB_HOST"
echo "Пользователь: $DB_USER"
echo ""
echo "SQL:"
echo "$SQL"
echo ""
read -p "Подтверждаете выполнение? (да/нет): " CONFIRM

if [ "$CONFIRM" != "да" ]; then
    echo "❌ Отменено"
    exit 1
fi

# Проверяем ping
if ! "$SCRIPT_DIR/db_ping.sh" > /dev/null 2>&1; then
    echo "ОШИБКА: Нет доступа к БД. Выполните bin/db_ping.sh для диагностики" >&2
    exit 1
fi

# Выполняем
echo "Выполняю..."
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" "$@"
