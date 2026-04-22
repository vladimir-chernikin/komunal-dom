# ДИАГНОСТИКА И ТРАССИРОВКА

## DialogTraceService - Микросервис трассировки

**Файл:** `/var/www/komunal-dom_ru/dialog_trace_service.py`

**Назначение:** Трассировка диалогов для диагностики работы AI-системы.

**Запуск:**
```bash
python dialog_trace_service.py --session-id web_123_abc
python dialog_trace_service.py --telegram-user-id 123456789
python dialog_trace_service.py --session-id web_123_abc --output json --limit 100
```

**Показывает:**
1. Результаты микросервисов (TagSearch, VectorSearch, SemanticSearch, AI)
2. LLM промты
3. Установленные фильтры (location, category, incident)
4. Память диалога (DialogMemoryManager)

---

## TraceReportService - Генерация отчетов

**Файл:** `/var/www/komunal-dom_ru/trace_report_service.py`

**Назначение:** Генерация подробных отчетов по трассировке диалогов.

**Запуск (Python):**
```python
from trace_report_service import generate_dialog_trace
path = await generate_dialog_trace('telegram_123456')
```

**Запуск (командная строка):**
```bash
python trace_report_service.py telegram_123456
```

**КРИТИЧЕСКОЕ ПРАВИЛО:**
При запросе "трассировки по шаблону":
1. ВСЕГДА создавай файл `/tmp/_tras_diag_ГГГГММДД_ЧЧММСС.md`
2. Используй `TraceReportService.generate_trace_report()`
3. Покажи путь к файлу
4. Установи `chmod 644`

**Просмотр:**
- http://komunal-dom.ru/admin-uk/dialog-trace/
- `cat /tmp/_tras_diag_*.md`

---

## Шаблон отчета трассировки

**Файл генерации:** `/var/www/komunal-dom_ru/trace_report_service.py`

**Основные разделы отчета:**
- Заголовок (session_id, канал, период)
- История txtPrb
- Детальная трассировка по сообщениям (анализ, микросервисы, фильтры, METADATA, ответ бота)
- Статистика диалога

**КРИТИЧЕСКИ ВАЖНЫЕ ИЗМЕНЕНИЯ (2025-12-28):**
1. **История txtPrb** - показывать на КАЖДОМ шаге
2. **Детальная расшифровка METADATA** - каждый блок с пояснением
3. **Candidates** - группировка по микросервисам
4. **Блок фильтров** - запрос/ответ LLM + фактические фильтры
5. **Определение значимой информации** - исправить неверное определение

Полный шаблон см. в `trace_report_service.py`

---

## TestBotSimulator - Имитатор пользователя

**Файл:** `test_bot_simulator.py`

**Назначение:** Тестирование системы в режиме имитации пользователя.

**Запуск:**
```bash
cd /var/www/komunal-dom_ru
source venv/bin/activate
python test_bot_simulator.py
```

**Сценарий "proryv_trub":**
- "привет"
- "у меня прорвало трубу"
- "в квартире"

**Результаты:**
- **SUCCESS** - однозначно определено
- **AMBIGUOUS** - требуется уточнение
- **ERROR** - ошибка

---

## WEB-ИНТЕРФЕЙС ЧАТА

### Django веб-чат

**URL:** http://komunal-dom.ru/chat/ (требуется авторизация)

**Файлы:**
- `message_handler/views.py`
- `message_handler/urls.py`
- `message_handler/templates/message_handler/chat.html`

**Использование:**
1. Авторизоваться
2. Открыть /chat/
3. Начать общение
