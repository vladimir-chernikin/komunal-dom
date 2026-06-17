#!/bin/bash

# Активация виртуального окружения
source venv/bin/activate

# Управление Django проектом
case "$1" in
    run)
        echo "Запуск Django сервера..."
        python manage.py runserver 0.0.0.0:8000
        ;;
    migrate)
        echo "Применение миграций..."
        python manage.py makemigrations
        python manage.py migrate
        ;;
    collectstatic)
        echo "Сбор статических файлов..."
        python manage.py collectstatic --noinput
        ;;
    createsuperuser)
        echo "Создание суперпользователя..."
        python manage.py createsuperuser
        ;;
    shell)
        echo "Запуск Django shell..."
        python manage.py shell
        ;;
    *)
        echo "Использование: $0 {run|migrate|collectstatic|createsuperuser|shell}"
        echo ""
        echo "Команды:"
        echo "  run           - Запустить сервер разработки"
        echo "  migrate       - Применить миграции базы данных"
        echo "  collectstatic - Собрать статические файлы"
        echo "  createsuperuser - Создать суперпользователя"
        echo "  shell         - Запустить Django shell"
        exit 1
        ;;
esac