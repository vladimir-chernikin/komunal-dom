# DB_AND_MODELS - Коммунальный Дом

**Дата:** 2026-03-19
**База данных:** PostgreSQL 16
**Имя БД:** aspect_objects_db
**Пользователь:** aspect_db

---

## 1. КЛЮЧЕВЫЕ СУЩНОСТИ БД

### Критические для продукта:

| Сущность | Таблица | App | Назначение |
|---|---|---|---|
| **dialog_logs** | MessageLog | message_handler | Лог всех сообщений |
| **services_catalog** | ServicesCatalog | portal (unmanaged) | Каталог услуг (68 услуг) |
| **communicativescript** | CommunicativeScript | message_handler | Скрипты бота |
| **prompttemplate** | PromptTemplate | llm_tester | Промпты для тестирования |
| **aiprompt** | AIPrompt | portal | AI промпты бота |
| **userprofile** | UserProfile | portal | Профили пользователей |

### Справочники (ref_*):

| Сущность | Таблица | App | Назначение |
|---|---|---|---|
| **ref_categories** | - | (существующая) | Категории услуг |
| **ref_objects** | - | (существующая) | Объекты (квартира, подъезд) |
| **ref_service_types** | - | (существующая) | Типы услуг |
| **ref_localization** | - | (существующая) | Локализация (индивидуальное/общедомовое) |
| **company** | Company | nsi | Компании |
| **equipmenttype** | EquipmentType | nsi | Виды оборудования |

---

## 2. DETАЛЬНЫЙ ОБЗОР МОДЕЛЕЙ

### Portal (portal/models.py - 219 строк)

#### AIPrompt

**Назначение:** AI промпты для бота

**Типы:**
- `system` - Системный промпт
- `greeting` - Приветствие
- `address_check` - Проверка адреса
- `address_not_found` - Адрес не найден
- `farewell` - Прощание
- `error` - Ошибка
- `profanity_warning` - Предупреждение о ругательствах
- `default` - Ответ по умолчанию

**Поля:**
- `prompt_id` - ID промпта (unique)
- `prompt_type` - Тип промпта
- `title` - Название
- `description` - Описание
- `content` - Содержание промпта
- `is_active` - Активен
- `is_test` - Тестовый (для экспериментов)
- `created_by` - Создал (FK → User)

**Использование:** Вероятно, для Telegram бота

#### UserProfile

**Назначение:** Расширенный профиль пользователя

**Роли:**
- `resident` - Житель
- `uk_user` - Пользователь УК
- `direktor_uk` - Директор УК
- `django_admin` - Администратор Django (ИТ)
- `executor` - Исполнитель

**Поля:**
- `user` - Пользователь (OneToOne → User)
- `role` - Роль
- `timezone` - Часовой пояс
- `phone` - Телефон
- `address` - Адрес
- `specialization` - Специализация исполнителя
- `job_title` - Должность
- `responsibilities` - Обязанности

**Методы:**
- `is_uk_user()` - Проверка: пользователь УК
- `is_uk_admin()` - Проверка: админ УК
- `is_director_uk()` - Проверка: директор УК
- `is_django_admin()` - Проверка: Django админ
- `has_admin_access()` - Проверка: доступ к админке

#### SemanticPattern

**Назначение:** Семантический паттерн для классификации сообщений

**Типы:**
- `incident` - Инцидент/Авария
- `water` - Водоснабжение/Канализация
- `electricity` - Электричество
- `heating` - Отопление
- `gas` - Газ
- `elevator` - Лифт
- `door` - Двери/Замки
- `window` - Окна
- `roof` - Крыша
- `other` - Другое

**Поля:**
- `pattern_type` - Тип паттерна
- `keyword` - Ключевое слово
- `weight` - Вес (0.1 - 10.0, отрицательный = инверсия)
- `is_active` - Активен
- `notes` - Заметки

**Уникальность:** `pattern_type + keyword`

**Использование:** Возможно, вытеснен CommunicativeScript?

#### ServicesCatalog (unmanaged)

**Назначение:** Услуги из существующей БД services_catalog

**Поля:**
- `service_id` - ID услуги (PK)
- `scenario_id` - ID сценария
- `scenario_name` - Название услуги
- `type_id` - Тип услуги (FK → ref_service_types)
- `kind_id` - Вид услуги
- `localization_id` - Локализация (FK → ref_localization)
- `category_id` - Категория (FK → ref_categories)
- `object_id` - Объект (FK → ref_objects)
- `payment_id` - Оплата
- `route_id` - Legacy-поле исходного каталога услуг; в маршрутизации заявок не используется
- `urgency_id` - Срочность
- `description_for_search` - Описание для поиска
- `is_active` - Активна
- `embedding_service` - Embedding услуги (JSON: 256 float)
- `embedding_text` - Текст для векторизации
- `tags` - Теги через запятую

**Managed:** False (таблица уже существует)

**Связи:** ref_categories, ref_objects, ref_service_types, ref_localization

---

### Message Handler (message_handler/models.py - 458 строк)

#### MessageLog

**Назначение:** Лог всех сообщений от пользователей и ответов бота

**Каналы:**
- `telegram` - Telegram
- `whatsapp` - WhatsApp
- `maxchat` - Мессенджер Макс
- `web` - Веб-сайт
- `test_bot` - Тестовый бот-имитатор
- `transcriber` - Голосовой транскрибатор
- `api` - Внешнее API

**Направления:**
- `inbound` - Входящее (от пользователя)
- `outbound` - Исходящее (от бота)
- `system` - Системное

**Поля:**
- `dialog_id` - ID диалога (UUID)
- `channel` - Канал связи
- `direction` - Направление
- `message_id` - ID сообщения в канале
- `session_id` - ID сессии диалога
- `user_id` - ID пользователя в канале
- `django_user_id` - ID пользователя Django
- `message_type` - Тип сообщения
- `message_content` - Текст сообщения
- `processing_stage` - Стадия обработки
- `confidence_score` - Уверенность определения
- `service_detected_id` - ID определенной услуги
- `address_extracted` - Извлеченный адрес (JSON)
- `processing_time_ms` - Время обработки (мс)
- `llm_provider` - LLM провайдер
- `llm_model` - LLM модель
- `tokens_used` - Количество токенов
- `cost_rub` - Стоимость (руб)
- `metadata` - Метаданные (JSON: service_detection, txtPrb, filters)
- `timestamp` - Время получения

**Таблица:** `dialog_logs` (существующая)

**Индексы:** channel, session_id, user_id, dialog_id, message_type, timestamp

**Методы:**
- `get_context_history(limit=10)` - Получить историю диалога

#### CommunicativeScript

**Назначение:** Коммуникативный скрипт для бота

**Типы:**
- `fallback` - Fallback при ошибке AI
- `pause` - Заполнение паузы (audio)
- `greeting` - Приветствие
- `clarification` - Уточняющий вопрос
- `confirmation` - Подтверждение
- `error` - Сообщение об ошибке

**Каналы:**
- `telegram` - Telegram
- `audio` - Аудио (телефон)
- `both` - Оба канала

**Поля:**
- `script_name` - Название скрипта (unique)
- `script_type` - Тип скрипта
- `channel` - Канал связи
- `text` - Текст скрипта
- `conditions` - Условия использования (JSON)
- `priority` - Приоритет
- `max_uses_per_day` - Макс. использований/день (-1 = без ограничений)
- `min_dialog_turn` - Мин. номер хода
- `max_dialog_turn` - Макс. номер хода (-1 = без ограничений)
- `is_active` - Активен
- `category` - Категория
- `notes` - Заметки

**Индексы:** script_type, channel, is_active

#### APIErrorLog

**Назначение:** Лог ошибочных запросов к внешнему API

**Типы ошибок:**
- `auth` - Ошибка аутентификации
- `validation` - Ошибка валидации
- `processing` - Ошибка обработки
- `timeout` - Таймаут
- `internal` - Внутренняя ошибка

**Поля:**
- `error_type` - Тип ошибки
- `status_code` - HTTP статус
- `error_message` - Ошибка
- `error_details` - Детали ошибки (traceback)
- `session_id` - Session ID
- `request_id` - Request ID (unique)
- `client_ip` - IP клиента
- `client_system` - Клиентская система
- `token_preview` - Токен (первые символы)
- `request_data` - Данные запроса (JSON)
- `message_preview` - Сообщение (первые символы)
- `user_id` - User ID
- `nomer` - NOMER (абонент)
- `timestamp` - Время ошибки

**Индексы:** timestamp, client_ip, session_id, client_system, error_type, nomer

---

### LLM Tester (llm_tester/models.py - 241 строка)

#### PromptTemplate

**Назначение:** Шаблоны промптов для тестирования микросервисов

**Типы:**
- `filter_detection` - FilterDetectionService
- `main_agent` - MainAgent
- `problem_accumulation` - ProblemAccumulationService
- `custom` - Кастомный

**Поля:**
- `name` - Название промпта
- `slug` - Slug (может быть несколько версий с одинаковым slug)
- `prompt_type` - Тип промпта
- `microservice` - Микросервис (для связки с логами)
- `template` - Шаблон промпта (с переменными {variable_name})
- `description` - Описание
- `parent_version` - Предыдущая версия (FK → self)
- `version_number` - Номер версии (1, 2, 3, ...)
- `is_active` - Активен

**Версионирование:** Да (parent_version + version_number)

**Уникальность:** slug может дублироваться (разные версии)

#### LLMRequestLog

**Назначение:** Лог запросов к LLM (добавлен позднее)

**Поля:**
- `request_id` - Request ID
- `provider` - Провайдер (YandexGPT, GigaChat, ...)
- `model` - Модель
- `service_name` - Имя микросервиса
- `prompt_text` - Текст промпта
- `response_text` - Текст ответа
- `tokens_used` - Количество токенов
- `cost_rub` - Стоимость (руб)
- `duration_ms` - Длительность (мс)
- `status` - Статус (success, error, timeout)
- `error_message` - Ошибка
- `metadata` - Метаданные (JSON)
- `created_at` - Создан

**Использование:** Для отладки и анализа стоимости LLM

---

### NSI (nsi/models.py - 39 строк)

#### Company

**Назначение:** Справочник компаний

**Поля:**
- `name` - Наименование
- `full_name` - Полное наименование
- `domain` - Домен
- `phone` - Телефон для приема заявок
- `is_active` - Активна
- `created_at` - Создана
- `updated_at` - Обновлена

#### EquipmentType

**Назначение:** Справочник видов общедомового оборудования

**Поля:**
- `name` - Наименование
- `description_for_llm` - Описание для LLM (для использования в AI-системе)
- `is_active` - Активен
- `created_at` - Создан
- `updated_at` - Обновлен

---

### File Manager (file_manager/models.py - 28 строк)

#### FileMetadata

**Назначение:** Метаданные загруженных файлов

**Поля:**
- `file` - Файл
- `filename` - Имя файла
- `file_type` - Тип файла
- `file_size` - Размер файла
- `uploaded_at` - Загружен
- `uploaded_by` - Загружен кем (FK → User)

---

### Kladr (kladr/models.py - 156 строк)

#### KladrAddress

**Назначение:** Адреса из базы КЛАДР

**Поля:**
- `kladr_code` - Код КЛАДР
- `region_name` - Область
- `district_name` - Район
- `city_name` - Город
- `settlement_name` - Населенный пункт
- `street_name` - Улица
- `house_number` - Номер дома
- `full_address` - Полный адрес
- `is_active` - Активен

**Количество:** 2,615 адресов

#### KladrStreet

**Назначение:** Улицы из базы КЛАДР

**Поля:**
- `street_name` - Название улицы
- `kladr_code` - Код КЛАДР
- `is_active` - Активен

---

### Database Viewer (database_viewer/models.py - 3 строки)

#### SavedQuery

**Назначение:** Сохраненные SQL запросы

**Поля:**
- `name` - Название запроса
- `sql_query` - SQL запрос
- `created_by` - Создал (FK → User)
- `created_at` - Создан

---

## 3. СВЯЗИ МЕЖДУ ТАБЛИЦАМИ

### Основные связи:

```
User (Django)
└── UserProfile (OneToOne)

MessageLog
├── django_user_id → User (FK, nullable)
└── service_detected_id → services_catalog (FK, nullable)

ServicesCatalog (unmanaged)
├── category_id → ref_categories (FK)
├── object_id → ref_objects (FK)
├── type_id → ref_service_types (FK)
└── localization_id → ref_localization (FK)

PromptTemplate
└── parent_version → PromptTemplate (self, FK)

AIPrompt
└── created_by → User (FK, nullable)

CommunicativeScript
(явных связей нет)

APIErrorLog
(явных связей нет)
```

### Проблемные места:

1. **ServicesCatalog (unmanaged)** - не управляется Django, риск рассинхрона
2. **Нет явных связей** для CommunicativeScript → services_catalog
3. **Нет связей** MessageLog → CommunicativeScript (какой скрипт использовался?)
4. **Дублирование промптов** - AIPrompt (portal) vs PromptTemplate (llm_tester)

---

## 4. МЕРТВЫЕ МОДЕЛИ / ПОДОЗРИТЕЛЬНЫЕ МЕСТА

### SemanticPattern (portal)

**Проблема:** Возможно, вытеснен CommunicativeScript

**Признаки:**
- Похожая функциональность (паттерны vs скрипты)
- Нет связей с MessageLog
- Не используется в основных flows

**Рекомендация:** Проверить использование, если не используется - удалить

### AIPrompt (portal)

**Проблема:** Дублирует PromptTemplate (llm_tester)

**Признаки:**
- Два хранилища промптов
- Неясно, какой использовать
- Нет связей между ними

**Рекомендация:** Унифицировать, оставить один

---

## 5. ПОДОЗРИТЕЛЬНЫЕ МЕСТА

### Unmanaged модели:

1. **ServicesCatalog (portal)** - managed=False, таблица уже существует
   - **Риск:** Рассинхрон с реальной БД
   - **Рекомендация:** Добавить миграции для версионирования

### Отсутствующие связи:

1. **MessageLog → CommunicativeScript** - какой скрипт использовался?
2. **MessageLog → PromptTemplate** - какой промпт использовался?
3. **ServicesCatalog → CommunicativeScript** - нет явной связи

### Дублирование:

1. **AIPrompt (portal) vs PromptTemplate (llm_tester)** - два хранилища промптов
2. **SemanticPattern (portal) vs CommunicativeScript (message_handler)** - похожая функциональность

---

## 6. РУДИМЕНТЫ В БД

### Потенциальные рудименты:

1. **SemanticPattern** - если не используется, удалить
2. **AIPrompt** - если вытеснен PromptTemplate, удалить
3. **ref_*** таблицы - если не используются, проверить

### Требуют проверки:

1. **Все поля metadata (JSON)** - что там хранится?
   - MessageLog.metadata
   - CommunicativeScript.conditions
   - APIErrorLog.request_data

2. **Все embedding поля (JSON)** - корректность данных
   - ServicesCatalog.embedding_service (256 float)
   - ServicesCatalog.embedding_text

---

## 7. ЧТО НУЖНО ПРОВЕРИТЬ ВРУЧНУЮ

### SQL запросы для проверки:

```sql
-- Проверить SemanticPattern - используется ли?
SELECT COUNT(*) FROM portal_semanticpattern WHERE is_active = true;

-- Проверить AIPrompt - используется ли?
SELECT COUNT(*) FROM portal_aiprompt WHERE is_active = true;

-- Проверить CommunicativeScript - сколько активных?
SELECT script_type, COUNT(*) FROM message_handler_communicativescript
WHERE is_active = true GROUP BY script_type;

-- Проверить MessageLog - сколько записей?
SELECT channel, COUNT(*) FROM dialog_logs GROUP BY channel;

-- Проверить embedding - есть ли NULL?
SELECT COUNT(*) FROM services_catalog WHERE embedding_service IS NULL;

-- Проверить PromptTemplate - сколько версий?
SELECT slug, COUNT(*) FROM llm_tester_prompttemplate
GROUP BY slug HAVING COUNT(*) > 1;
```

### Проверить целостность связей:

```sql
-- Есть ли orphaned MessageLog (нет пользователя)?
SELECT COUNT(*) FROM dialog_logs WHERE django_user_id IS NULL;

-- Есть ли MessageLog с несуществующим service_detected_id?
SELECT COUNT(*) FROM dialog_logs
WHERE service_detected_id IS NOT NULL
AND service_detected_id NOT IN (SELECT service_id FROM services_catalog);
```

---

## 8. РЕКОМЕНДАЦИИ

### Минимальные изменения:

1. **Проверить использование SemanticPattern** - если нет, удалить
2. **Проверить использование AIPrompt** - если вытеснен PromptTemplate, удалить
3. **Добавить связи** MessageLog → CommunicativeScript, MessageLog → PromptTemplate

### Средние изменения:

1. **Унифицировать промпты** - объединить AIPrompt и PromptTemplate
2. **Добавить миграции** для ServicesCatalog (unmanaged → managed)
3. **Нормализовать metadata** - выделить в отдельные поля

### Сложные изменения:

1. **Рефакторинг models** - разбить на более мелкие
2. **Добавить constraints** - CHECK, FK с CASCADE
3. **Добавить indexes** - для оптимизации запросов

---

## 9. СТАТИСТИКА БД

| Таблица | Примерное количество записей |
|---|---|
| dialog_logs | 10,000+ (логирование всех сообщений) |
| services_catalog | 68 (фиксированное количество услуг) |
| communicativescript | 20-50 (скрипты бота) |
| prompttemplate | 50-100 (промпты для тестирования) |
| aiprompt | 10-20 (промпты бота) |
| semanticpattern | 50-100 (паттерны) |
| kladraddress | 2,615 (адреса) |
| userprofile | 10-50 (пользователи) |
| apierrorlog | 100-500 (логи ошибок) |

---

**ВЫВОД:** БД имеет четкую структуру с 15+ моделями, но страдает от дублирования (AIPrompt vs PromptTemplate, SemanticPattern vs CommunicativeScript) и отсутствия связей между ключевыми таблицами. Главные проблемы: ServicesCatalog (unmanaged), отсутствие явных связей, дублирование промптов. Quick wins: проверить использование SemanticPattern и AIPrompt, добавить связи MessageLog → CommunicativeScript.
