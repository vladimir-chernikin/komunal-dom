# Настройка поддомена aspect.komunal-dom.ru

## Nginx конфигурация

Файл: `/etc/nginx/sites-available/komunal-dom.ru`

```nginx
server {
    listen 80;
    server_name komunal-dom.ru www.komunal-dom.ru aspect.komunal-dom.ru;
    ...
}
```

## Локальное тестирование (/etc/hosts)

Добавить в `/etc/hosts`:
```
127.0.0.1	komunal-dom.ru www.komunal-dom.ru aspect.komunal-dom.ru
```

## Production DNS

Для работы в production нужно настроить DNS запись:

```
aspect A <IP-адрес сервера>
```

IP-адрес должен быть тем же, что и у komunal-dom.ru.

## Результат

- `http://komunal-dom.ru/` → landing page (форма входа + выбор компании)
- `http://www.komunal-dom.ru/` → landing page
- `http://aspect.komunal-dom.ru/` → aspect landing page (информация об УК)

## Middleware

Файл: `komunal_dom/middleware.py`

Обрабатывает поддомены и перенаправляет:
- `aspect.komunal-dom.ru` → `aspect_landing()`
- другие → обычная логика
