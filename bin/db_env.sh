#!/bin/bash
# DB_ENV - Загрузка DB credentials из .env
# Использование: source bin/db_env.sh

set -euo pipefail

# Переходим в корень проекта
cd "$(dirname "$0")/.."

# Проверяем наличие .env
if [ ! -f .env ]; then
    echo "ОШИБКА: .env файл не найден" >&2
    exit 1
fi

# Загружаем переменные из .env (НЕ печатаем пароль!)
export $(grep -v '^#' .env | grep -v '^$' | xargs)

# Проверяем обязательные переменные
if [ -z "${DB_NAME:-}" ]; then
    echo "ОШИБКА: DB_NAME не задан в .env" >&2
    exit 1
fi

if [ -z "${DB_USER:-}" ]; then
    echo "ОШИБКА: DB_USER не задан в .env" >&2
    exit 1
fi

if [ -z "${DB_PASSWORD:-}" ]; then
    echo "ОШИБКА: DB_PASSWORD не задан в .env" >&2
    exit 1
fi

# Дефолтные значения для необязательных переменных
export DB_HOST="${DB_HOST:-localhost}"
export DB_PORT="${DB_PORT:-5432}"

# Успех - переменные загружены (не печатаем пароль!)
# Проверка: echo "DB_NAME=$DB_NAME, DB_USER=$DB_USER, DB_HOST=$DB_HOST, DB_PORT=$DB_PORT"
