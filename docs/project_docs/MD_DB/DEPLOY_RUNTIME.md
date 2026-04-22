# РАЗВЕРТЫВАНИЕ И RUNTIME

## Стек

- **ОС:** Ubuntu server
- **Web-сервер:** nginx (порт 80)
- **App-сервер:** gunicorn (127.0.0.1:8000, 3 workers)
- **База данных:** PostgreSQL 16
- **Фреймворк:** Django 6.0
- **Python:** venv

---

## Django управление

**Рабочая директория:** `/var/www/komunal-dom_ru`

**Управление:**
```bash
cd /var/www/komunal-dom_ru
source venv/bin/activate
./manage.sh run              # Запуск dev-сервера
./manage.sh migrate          # Миграции
./manage.sh shell            # Django shell
./manage.sh collectstatic    # Сбор статических файлов
```

---

## Production: nginx + gunicorn

### gunicorn (systemd сервис)

**Название сервиса:** `gunicorn-komunal-dom`

**Управление:**
```bash
# Перезапуск (после изменений .py файлов)
systemctl restart gunicorn-komunal-dom

# Проверка статуса
systemctl status gunicorn-komunal-dom

# Просмотр логов
journalctl -u gunicorn-komunal-dom -f
```

**КОГДА НУЖЕН RESTART:**
- ✅ После изменений `.py` файлов (views, models, services)
- ✅ После изменений настроек Django
- ✅ После добавления новых Django приложений

**КОГДА НЕ НУЖЕН RESTART:**
- ❌ Изменения `.html` шаблонов (nginx отдает напрямую)
- ❌ Изменения статических файлов
- ❌ Изменения `.css` и `.js` файлов

### nginx

**Управление:**
```bash
# Перезагрузка конфигурации (без разрыва соединений)
systemctl reload nginx

# Полный перезапуск
systemctl restart nginx

# Проверка конфигурации
nginx -t

# Проверка статуса
systemctl status nginx
```

---

## URL и доступы

**Основные URL:**
- http://komunal-dom.ru/ - главная страница
- http://komunal-dom.ru/admin/ - админка Django
- http://komunal-dom.ru/admin-uk/ - админка УК
- http://komunal-dom.ru/chat/ - веб-чат (требуется авторизация)
- http://komunal-dom.ru/files/ - файлы

---

## Telegram бот "Сигизмунд Лазоревич"

**Название:** Сигизмунд Лазоревич
**Username:** @KomunalkaProblemBot
**Файл:** `/var/www/komunal-dom_ru/address_bot.py`
**Сервис:** `address-bot.service`

**Функционал:** Проверка адресов, анализ с AI, интеграция с КЛАДР

**API:** YandexGPT (активен, см. .env)

**База КЛАДР:** 2,615 адресов

**Управление:**
```bash
systemctl status address-bot
systemctl restart address-bot
journalctl -u address-bot -f
```

**Команды:** `/start`, `/help`, проверка адреса в свободной форме

---

## Права доступа к файлам

### После создания файлов через Write tool

**КРИТИЧЕСКИ ВАЖНО:** Когда Claude создает файлы через Write tool, они создаются от root с правами 600.

**ОБЯЗАТЕЛЬНЫЙ КОД ПОСЛЕ Write tool:**
```bash
# Для Django шаблонов
chmod 644 /var/www/komunal-dom_ru/путь/к/файлу.html
chown olga:www-data /var/www/komunal-dom_ru/путь/к/файлу.html

# Для целых директорий
find /var/www/komunal-dom_ru/имя_приложения/templates/ -type f -name "*.html" -exec chmod 644 {} \;
chown -R olga:www-data /var/www/komunal-dom_ru/имя_приложения/templates/
```

**АВТОМАТИЧЕСКАЯ ПРОВЕРКА:**
1. Проверить владельца: `ls -la файл`
2. Если владелец `root:root` - исправить: `chown olga:www-data файл`
3. Если права `600` - исправить: `chmod 644 файл`
4. Перезапустить gunicorn: `systemctl restart gunicorn-komunal-dom`

**ОСОБЕННО ВАЖНО:** Django templates (`.html`), статические файлы, миграции - ВСЕ должно быть читаемым для `www-data`!

### Файлы в /tmp

**ОБЯЗАТЕЛЬНО:** После создания файлов в `/tmp` устанавливать права `chmod 644`.

**ПРИЧИНА:** Веб-сервер (nginx/gunicorn) работает от `www-data`, файлы с правами `600` недоступны.

**ОБЯЗАТЕЛЬНЫЙ КОД:**
```python
import os
output_path.write_text(content, encoding='utf-8')
os.chmod(output_path, 0o644)  # rw-r--r--
```

**КАКИЕ ФАЙЛЫ:** `_tras_diag_*.md`, `*_REPORT_*.md`, `*_ANALYSIS_*.md`, любые файлы в `/tmp` для веб-интерфейса

---

## Обязательное тестирование после правок

**ПРАВИЛО:** После редактирования файлов, которые используются Django views или веб-сервером, ВСЕГДА выполнять проверку.

**ОБЯЗАТЕЛЬНЫЕ ДЕЙСТВИЯ:**

1. **Права доступа на новые файлы:**
   ```bash
   chmod 755 /var/www/komunal-dom_ru/имя_приложения/templates/
   chmod 644 /var/www/komunal-dom_ru/имя_приложения/templates/**/*.html
   chown -R olga:www-data /var/www/komunal-dom_ru/имя_приложения/templates/
   ```

2. **Очистка кэша Python:**
   ```bash
   find /var/www/komunal-dom_ru/__pycache__ -name "*.pyc" -delete
   find /var/www/komunal-dom_ru -type d -name "__pycache__" -exec chmod -R 755 {} \;
   ```

3. **Перезапуск gunicorn:**
   ```bash
   systemctl restart gunicorn-komunal-dom
   systemctl status gunicorn-komunal-dom
   ```

4. **Проверка доступности страницы:**
   ```bash
   curl -I http://localhost:8000/путь/к/странице/
   ```

**КОГДА ВЫПОЛНЯТЬ:**
- ✅ После создания/изменения Django шаблонов
- ✅ После добавления новых Django приложений
- ✅ После изменения views.py или urls.py
- ✅ После добавления статических файлов
- ✅ После изменения middleware или context processors
