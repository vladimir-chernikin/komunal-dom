# Подсистема: Нормативный консультант

Дата: 2026-04-07

## Назначение

Подсистема отвечает за поиск и выдачу ответов по нормативным документам ЖКХ.

Ключевая особенность:
- UI находится в Django-проекте `komunal-dom_ru`;
- backend поиска фактически внешний относительно этого проекта.

## Точки входа

- `/regulatory-chat/`

## Реальная архитектура

### UI-слой в основном Django-проекте

Файлы:
- [portal/urls.py](/var/www/komunal-dom_ru/portal/urls.py)
- [portal/views.py](/var/www/komunal-dom_ru/portal/views.py)
- [portal/templates/portal/normative_chat.html](/var/www/komunal-dom_ru/portal/templates/portal/normative_chat.html)
- [static/js/normative-chat.js](/var/www/komunal-dom_ru/static/js/normative-chat.js)

Факты:
- `portal.urls` публикует `/regulatory-chat/`;
- `portal.views.regulatory_chat()` просто рендерит страницу;
- JS на странице делает HTTP-запросы наружу на `http://komunal-dom.ru:8002/search`.

### Proxy-слой

Файл:
- `/etc/nginx/sites-enabled/normativ-api.conf`

Факт:
- `listen 8002;`
- `proxy_pass http://127.0.0.1:8001/;`

### Внешний backend

Файлы:
- `/home/olga/normativ_docs/Волков/vector-db-test/backend/main_cpu.py`
- `/home/olga/normativ_docs/Волков/vector-db-test/backend/metrics.py`

Процесс:
- `python3 main_cpu.py`

Факты:
- порт `8001` реально слушается;
- процесс реально запущен;
- backend поднимает `FastAPI`;
- backend использует `FAISS`, `SentenceTransformer`, Yandex API.

## Что подтверждено по runtime

Пруфы:
- `ss -ltnp | grep ':8001'`
- `ps -ef | grep main_cpu.py`
- `curl -I http://127.0.0.1:8002/search` возвращает `405 Method Not Allowed`, то есть endpoint живой и ожидает POST.

## Таблицы основного Django-проекта

На текущем шаге не подтверждено прямое использование таблиц `aspect_objects_db` этой подсистемой.

Это значит:
- нельзя автоматически привязывать `regulatory-chat` к `ai_*` таблицам проекта;
- нельзя автоматически считать, что его данные хранятся в `dialog_logs` или `llm_request_log`.

## Что видно из backend

`main_cpu.py` подтверждает:
- отдельную FastAPI-службу;
- отдельную векторную базу `vectordb`;
- отдельную AI-логику переформулирования запроса;
- интеграцию с Yandex API;
- отдельную систему метрик.

Следствие:
- нормативный консультант надо считать отдельной внешней подсистемой;
- у него может быть своя собственная data-plane, не совпадающая с Django-проектом.

## Пересечения с основным проектом

### Через UI и авторизацию

- страница открывается из `portal`;
- пользователь заходит через основной сайт;
- но поиск уходит во внешний backend.

### Через инфраструктуру домена

- используется общий домен `komunal-dom.ru`;
- внешний backend проксируется тем же nginx.

### Через будущий концепт

- теоретически подсистема может позже получить общий слой пользователей, журналирования или billing;
- на текущем шаге это не подтверждено кодом.

## Legacy/риски

- backend физически живет вне каталога `/var/www/komunal-dom_ru`;
- концептуально это уже отдельная bounded context подсистема;
- но пользовательский вход к ней пока маскируется под обычную страницу портала;
- при рефакторинге легко ошибочно принять ее за часть Django-chat bot слоя.

## Предварительная целевая ответственность подсистемы

Подсистема "Нормативный консультант" должна отвечать за:
- поиск по нормативной базе;
- интерпретацию вопроса в юридических терминах;
- retrieval и формирование ответа по нормативным документам.

Она не должна смешиваться с:
- приемом аварийных заявок;
- АДС-статусами;
- внутренним lifecycle `work_order`.

