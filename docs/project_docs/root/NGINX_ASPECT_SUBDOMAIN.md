# Настройка поддомена aspect.komunal-dom.ru

## ✅ Статус: Настроено и проверено

**Дата:** 2026-03-18
**IP адрес:** 155.212.217.73

## DNS записи

Все три домена указывают на один и тот же IP:
```
komunal-dom.ru         A  155.212.217.73
www.komunal-dom.ru     A  155.212.217.73
aspect.komunal-dom.ru  A  155.212.217.73
```

## Nginx конфигурация

Файл: `/etc/nginx/sites-available/komunal-dom.ru`

```nginx
server {
    listen 80;
    server_name komunal-dom.ru www.komunal-dom.ru aspect.komunal-dom.ru;
    ...
}
```

## Middleware

Файл: `komunal_dom/middleware.py`

Обрабатывает поддомены и перенаправляет:
- `aspect.komunal-dom.ru` → `aspect_landing()`
- другие → обычная логика

## Проверка работоспособности

**HTTP статусы:**
- ✅ `komunal-dom.ru` → 200
- ✅ `www.komunal-dom.ru` → 200
- ✅ `aspect.komunal-dom.ru` → 200

**Title страниц:**
- ✅ `komunal-dom.ru` → "Вход в систему - УК 'Аспект'"
- ✅ `www.komunal-dom.ru` → "Вход в систему - УК 'Аспект'"
- ✅ `aspect.komunal-dom.ru` → "УК 'Аспект' - Управление многоквартирными домами"

**Функционал:**
- ✅ Landing страница: форма входа + выбор компании из справочника
- ✅ Aspect landing: информация об УК + список компаний из справочника
- ✅ Компании в БД: `nsi_company` (1 запись: ООО УК АСПЕКТ)

## Результат

- `http://komunal-dom.ru/` → landing page (форма входа + выбор компании)
- `http://www.komunal-dom.ru/` → landing page
- `http://aspect.komunal-dom.ru/` → aspect landing page (информация об УК)
