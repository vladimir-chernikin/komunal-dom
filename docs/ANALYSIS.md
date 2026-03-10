# АНАЛИЗ ВОПРОСОВ ПОЛЬЗОВАТЕЛЯ

## 1. СРАВНЕНИЕ: llm_request_log vs dialog_logs

### llm_request_log (16 записей)
**НАЗНАЧЕНИЕ:** Технические метрики LLM запросов
- `provider`, `model` - какая модель вызвана
- `prompt_text`, `response_text` - промпт и ответ
- `prompt_tokens`, `completion_tokens`, `total_tokens` - токены
- `cost_rub` - стоимость
- `status` - success/error/timeout

**ДЛЯ ЧЕГО:** Аналитика стоимости, токенов, ошибок LLM

### dialog_logs (0 записей!)
**НАЗНАЧЕНИЕ:** Бизнес-логика диалогов
- `dialog_id`, `user_id`, `session_id` - идентификаторы
- `message_type` (inbound/outbound/system) - тип сообщения
- `message_content` - текст сообщения
- `service_detected_id`, `confidence_score` - определенная услуга
- `processing_stage` - этап обработки
- `llm_provider`, `llm_model`, `tokens_used`, `cost_rub` - дублирует llm_request_log!

### ВЫВОД: Нужны ОБЕ таблицы

**llm_request_log** - для технической аналитики:
- Сколько потратили денег на LLM
- Какие модели используются
- Частота ошибок

**dialog_logs** - для бизнес-аналитики:
- История диалогов с пользователями
- Какие услуги определялись
- Сколько времени занимает обработка
- Путь пользователя к услуге

**Дублирование (`llm_*` поля в dialog_logs):** Это ссылка на llm_request_log, но нужно добавить `llm_request_id` для связи.

---

## 2. "Нет необходимости уточнять локацию" - АНАЛИЗ ПРИЧИНЫ

### РЕАЛЬНАЯ ПРИЧИНА:

Нужно посмотреть на КОНТЕКСТ сообщения "у меня течет":
1. Что вернул FilterDetectionService?
2. Какие established_filters были установлены?
3. Какой был txtPrb?

**ГИПОТЕЗА:** LLM увидела что "течет" - это про водоснабжение, а в кандидатах может быть только одна услуга про "течь" и она уже для ванной. Логика: "раз это течет, значит это водопроводная проблема, а все водопроводное - в ванной".

**НУЖНО ПРОТЕСТИРОВАТЬ:**
- Запустить TestBotSimulator с "у меня течет"
- Посмотреть какие filters установились
- Посмотреть какой candidates_json пришел в LLM

---

## 3. MessageHandlerService - СТАТУС

**НЕ УДАЛЕН!** Используется как ЕДИНАЯ точка входа:
- Файл: `message_handler_service.py`
- Строка 28: `class MessageHandlerService`
- Вызывается из: `message_handler/views.py`, `enhanced_aspect_bot.py`

**ФУНКЦИЯ:**
- Получает сообщение из любого канала
- Очищает сообщение (MessageCleanerService)
- Логирует в dialog_logs (через DialogLoggerService)
- Передает в MainAgent

---

## 4. MessageLog модель - ЗАЧЕМ НУЖНА

**Файл:** `message_handler/models.py`

**ПРОВЕРКА:**
```python
class MessageLog(models.Model):
    channel = models.CharField(...)
    direction = models.CharField(...)
    message_id = models.CharField(...)
    user_id = models.CharField(...)
    session_id = models.CharField(...)
    text = models.TextField(...)
    metadata = models.JSONField(...)
    django_user = models.ForeignKey(...)
```

**НАЗНАЧЕНИЕ:** Django ORM модель для таблицы `message_handler_messagelog`

**ПРОБЛЕМА:** Таблица `message_handler_messagelog` УСТАРЕЛА, теперь используется `dialog_logs`

**РЕШЕНИЕ:** Удалить модель И миграцию которая её создавала.

---

## 5. message_handler_messagelog - УДАЛИТЬ

**ПЛАН:**
1. Скопировать данные в `dialog_logs` (если нужно)
2. Удалить таблицу `message_handler_messagelog`
3. Удалить модель `MessageLog`
4. Удалить миграцию `0001_initial.py` в `message_handler`

---

## 6. dialog_memory_store vs dialog_logs - ДУБЛИРОВАНИЕ?

### dialog_memory_store (4 записи)
**НАЗНАЧЕНИЕ:** Память对话а (контекст)
- `context_json` - накопленная информация对话а
- `extracted_street`, `extracted_house_number` - адрес
- `current_service_id` - текущая выбранная услуга
- `dialog_status` - статус диалога (active, closed)
- `message_count`, `ai_requests_count` - счетчики

**ДЛЯ ЧЕГО:** DialogMemoryManager использует для хранения состояния между сообщениями

### dialog_logs (0 записей)
**НАЗНАЧЕНИЕ:** История всех сообщений (лог)
- Каждое сообщение отдельная запись
- Полная история对话а

### ВЫВОД: РАЗНЫЕ ТАБЛИЦЫ, НЕ ДУБЛИРУЮТ

- `dialog_memory_store` - ТЕКУЩЕЕ состояние (1 запись на диалог)
- `dialog_logs` - ИСТОРИЯ всех сообщений (много записей на диалог)

**АНАЛОГИЯ:**
- `dialog_memory_store` = Variables в программе
- `dialog_logs` = Log файл

---

## 7. Логирование LLM в AIAgentService - ПРАВИЛЬНО!

**ПОЛЬЗОВАТЕЛЬ ПРАВ:**

### Уже РЕАЛИЗОВАНО в AIAgentService:
Файл: `ai_agent_service.py`, строки 510-549
```python
async def _save_statistics_to_db(...)
    cursor.execute("""
        INSERT INTO llm_request_log (...)
    """)
```

**ВЫВОД:** Логирование УЖЕ есть в AIAgentService!
- Каждый вызов `call_llm()` → `_save_statistics_to_db()`
- Пишет в `llm_request_log`
- Дублировать в MainAgent НЕ НУЖНО

---

## 8. Миграция 0001_initial.py - ЧТО ЭТО

**Файл:** `message_handler/migrations/0001_initial.py`

**СОДЕРЖИМОЕ:**
```python
class Migration(migrations.Migration):
    initial = True

    operations = [
        migrations.CreateModel(
            name='MessageLog',
            fields=[...]
        )
    ]
```

**НАЗНАЧЕНИЕ:** Создает модель `MessageLog` и таблицу `message_handler_messagelog`

**ПОЧЕМУ ХОТЕЛ УДАЛИТЬ:** Таблица устарела, теперь используется `dialog_logs`

---

## 9. Legacy - ЧТО ЭТО

**Legacy** = Устаревший код, который нужно удалить

**ПРИМЕРЫ В ЭТОМ ПРОЕКТЕ:**
- `message_handler_messagelog` таблица (устарела, заменена на `dialog_logs`)
- `MessageLog` модель Django (устарела)
- `0001_initial.py` миграция (создает устаревшую таблицу)
- Папка `old/` со старыми файлами

---

## 10. Intersection (Воронка точности) - АЛГОРИТМ

**Файл:** `main_agent.py`, метод `_orchestrate_microservices` (строка 1826)

### АЛГОРИТМ:

```
1. TagSearchService → находит услуги по тегам
   Вернул: [5, 7, 25]

2. VectorSearchService → семантический поиск
   Вернул: [7, 25, 26]

3. SemanticSearchService → логико-семантический поиск
   Вернул: [5, 25]

4. AIAgentService → LLM поиск
   Вернул: [25]

══════════════════════════════════
ПЕРЕСЕЧЕНИЕ (Intersection):
══════════════════════════════════

TagSearch:       {5, 7, 25}
VectorSearch:    {7, 25, 26}
SemanticSearch: {5, 25}
AI:              {25}

Intersection = {5, 7, 25} ∩ {7, 25, 26} ∩ {5, 25} ∩ {25}
            = {25}

РЕЗУЛЬТАТ: Услуга ID=25 (присутствует во всех 4 сервисах)
```

### ЛОГИКА:
- Если 1 кандидат в intersection → SUCCESS
- Если несколько → AMBIGUOUS (уточнение)
- Если 0 → no_intersection ( fallback)

**НАЗВАНИЕ:** "Воронка точности" - чем больше сервисов нашли услугу, тем точнее результат
