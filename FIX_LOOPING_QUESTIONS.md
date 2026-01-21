# ИСПРАВЛЕНО: Зацикливание и глупые вопросы бота

**Дата:** 2026-01-21
**Проблема:** Бот зацикливается и задаёт вопросы на уже известные ответы
**Статус:** ✅ ИСПРАВЛЕНО

---

## Пример проблемного диалога (БЕЗ исправления)

```
Пользователь: "У меня на кухне пахнет газом"
txtPrb: "на кухне пахнет газом"

Бот: "В какой комнате проблема?" ← ГЛУПЫЙ ВОПРОС! Кухня же уже указана!

Пользователь: "На кухне" (повторяет)

Бот: "Где утечка газа?"

Пользователь: "да"

Бот: "В какой комнате проблема?" ← ПОВТОР!
```

---

## Корень проблемы

**Проблема 1: Защита от зацикливания**
- ❌ `CommunicativeScriptsService` отключен в `main_agent.py:145`
- ❌ Скрипты в БД имели `max_dialog_turn=-1` (бесконечность)
- ❌ Защита в `communicative_scripts_service.py` не работала (сервис отключен)

**Проблема 2: Глупые вопросы**
- ❌ `txtPrb` содержал "на кухне пахнет газом" (локация "кухня" ЕСТЬ)
- ❌ LLM генерировал вопрос "В какой комнате проблема?"
- ❌ `_llm_validate_question` НЕ проверял вопросы о локации
- ❌ Список `generic_questions` не содержал "В какой комнате", "Где именно"

---

## Что исправлено

### Исправление 1: Защита от зацикливания (КОММИТ `75cd7bc`)

**Файл:** `main_agent.py:3418`

```python
# ИСПРАВЛЕНИЕ (2026-01-21): Защита от зацикливания
dialog_turn = len(dialog_history) if dialog_history else 1
if dialog_turn >= 7:
    logger.warning(
        f"[ANTI-LOOP] Слишком много AI-вопросов (turn={dialog_turn}) -> "
        f"возвращаем финальное сообщение о передаче оператору"
    )
    final_message = "К сожалению, я не смог определить вашу проблему..."
    return {
        'question': final_message,
        'prompt': '[ANTI-LOOP] Превышен лимит попыток',
        'response': final_message,
        'model': 'anti-loop',
        'usage': {}
    }
```

**Результат:**
- ✅ После 7 ходов бот возвращает финальное сообщение
- ✅ Логирование `[ANTI-LOOP]` для отладки
- ✅ Бесконечные циклы предотвращены

---

### Исправление 2: Скрипты в БД (КОММИТ `1499951`)

**Файл:** `message_handler/migrations/fix_communicative_scripts_loop.sql`

```sql
-- Обновляем fallback скрипты: ограничиваем количество повторений до 5
UPDATE message_handler_communicativescript
SET max_dialog_turn = 5
WHERE script_name IN (
    'fallback_followup_clarify',
    'fallback_clarify_location',
    'fallback_clarify_object',
    'fallback_clarify_details'
);

-- Создаем финальный fallback скрипт (с 6 хода)
INSERT INTO message_handler_communicativescript (...)
VALUES (
    'fallback_final_operator',
    ...,
    min_dialog_turn = 6,
    text = 'К сожалению, я не смог определить вашу проблему. Пожалуйста, свяжитесь с оператором.'
);
```

**Результат:**
- ✅ Fallback скрипты ограничены до 5 ходов
- ✅ С 6 хода: финальное сообщение о передаче оператору
- ✅ Бесконечные циклы предотвращены на уровне БД

---

### Исправление 3: Блокировка вопросов о локации (КОММИТ `b9450e1`)

**Файл:** `main_agent.py:2452-2493`

```python
# ИСПРАВЛЕНИЕ (2026-01-21): Блокируем вопросы о локации, если она уже известна в txtPrb
location_questions = [
    'в какой комнат',
    'где именно',
    'в каком мест',
    'какое помещение',
    'в каком помещении',
    'где проблем',
    'локаци',
    'местонахождени'
]

if any(phrase in question_lower for phrase in location_questions):
    txtPrb_lower = txtPrb.lower()

    # Проверяем, есть ли в txtPrb слова локации
    location_words = [
        'кухн', 'зал', 'ванная', 'туалет', 'спальн', 'комнат',
        'прихож', 'коридор', 'балкон', 'лодж', 'подъезд', 'подвал',
        'чердак', 'кровл', 'фасад', 'двор', 'улиц', 'квартир',
        'дом', 'подъезд'
    ]

    if any(word in txtPrb_lower for word in location_words):
        logger.warning(f"⚠️ DETECTED LOCATION QUESTION BUT LOCATION ALREADY KNOWN!")
        logger.warning(f"⚠️ Question: '{question}'")
        logger.warning(f"⚠️ txtPrb: '{txtPrb}'")

        # Генерируем вопрос на основе того, что известно
        if any(word in txtPrb_lower for word in ['запах', 'воняет', 'пахнет', 'газ']):
            question = 'Откуда именно запах или утечка?'
        elif any(word in txtPrb_lower for word in ['капает', 'течет', 'льет', 'протека']):
            question = 'Что именно течет или откуда утечка?'
        elif any(word in txtPrb_lower for word in ['сломал', 'не работ', 'испортил']):
            question = 'Что именно сломалось или не работает?'
        elif any(word in txtPrb_lower for word in ['шум', 'гремит', 'стучит']):
            question = 'Что именно шумит или где источник шума?'
        else:
            question = 'Уточните детали проблемы.'

        logger.warning(f"✅ REPLACED WITH: '{question}'")
        return question
```

**Результат:**
- ✅ Вопросы "В какой комнате?", "Где именно?" БЛОКИРУЮТСЯ при известной локации
- ✅ Генерируются КОНТЕКСТНЫЕ вопросы на основе txtPrb
- ✅ Логирование для отладки

---

## Пример диалога С исправлением

```
Пользователь: "У меня на кухне пахнет газом"
txtPrb: "на кухне пахнет газом"

Логи:
⚠️ DETECTED LOCATION QUESTION BUT LOCATION ALREADY KNOWN!
⚠️ Question: 'В какой комнате проблема?'
⚠️ txtPrb: 'на кухне пахнет газом'
✅ REPLACED WITH: 'Откуда именно запах или утечка?'

Бот: "Откуда именно запах или утечка?" ← КОНТЕКСТНЫЙ ВОПРОС!

Пользователь: "Из трубы"
```

---

## Как протестировать

### Автотест:
```bash
cd /var/www/komunal-dom_ru
source venv/bin/activate
python test_anti_loop.py
```

### Ручная проверка:
1. Откройте веб-чат: http://komunal-dom.ru/chat/
2. Напишите: "У меня на кухне пахнет газом"
3. Ожидаемый вопрос: "Откуда именно запах или утечка?"
4. НЕ должно быть: "В какой комнате проблема?"

---

## Файлы

- **Инструкция:** `INSTRUCTIONS_TEST_ANTI_LOOP.md`
- **Тестовый скрипт:** `test_anti_loop.py`
- **Миграция БД:** `message_handler/migrations/fix_communicative_scripts_loop.sql`
- **Этот файл:** `FIX_LOOPING_QUESTIONS.md`

---

## Коммиты

1. `1499951` - Защита в communicative_scripts_service.py + миграция БД
2. `75cd7bc` - Защита в main_agent.py (_generate_ai_question)
3. `b9450e1` - Блокировка вопросов о локации (_llm_validate_question)

Ветка: `feature/tz-26-12-critical-fixes`

---

## Логирование

При срабатывании защит в логах появляется:

```
[ANTI-LOOP] Слишком много AI-вопросов (turn=7) -> возвращаем финальное сообщение
⚠️ DETECTED LOCATION QUESTION BUT LOCATION ALREADY KNOWN!
⚠️ Question: 'В какой комнате проблема?'
⚠️ txtPrb: 'на кухне пахнет газом'
✅ REPLACED WITH: 'Откуда именно запах или утечка?'
```

---

## Остались проблемы?

Если бот все равно зацикливается или задаёт глупые вопросы:

1. Соберите трассировку:
   ```bash
   python trace_report_service.py SESSION_ID
   ```

2. Проверьте логи:
   ```bash
   journalctl -u gunicorn-komunal-dom -f | grep -E "ANTI-LOOP|DETECTED LOCATION"
   ```

3. Отправьте мне:
   - Файл трассировки: `/tmp/_tras_diag_ГГГГММДД_ЧЧММСС.md`
   - Session ID проблемного диалога
   - Логи за период зацикливания
