#!/bin/bash

# Активация виртуального окружения
source /var/www/komunal-dom_ru/venv/bin/activate

# Настройка переменных окружения
export DJANGO_SETTINGS_MODULE=komunal_dom.settings
export PYTHONPATH=/var/www/komunal-dom_ru:$PYTHONPATH

# Запуск gunicorn
exec gunicorn \
    --workers 3 \
    --worker-class sync \
    --worker-connections 1000 \
    --max-requests 1000 \
    --max-requests-jitter 100 \
    --bind 127.0.0.1:8000 \
    --chdir /var/www/komunal-dom_ru \
    komunal_dom.wsgi:application