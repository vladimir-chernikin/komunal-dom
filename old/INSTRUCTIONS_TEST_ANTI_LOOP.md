# ИНСТРУКЦИЯ: Тестирование защиты от зацикливания коммуникативных скриптов

**Дата:** 2026-01-21
**Задача:** Проверить, что бот не зацикливается на fallback вопросах

---

## Что исправлено

### 1. База данных (12 скриптов):
- **fallback скрипты:** ограничены до 5 ходов (max_dialog_turn=5)
- **clarification скрипты:** ограничены до 5 ходов
- **fallback_final_operator:** с 6 хода - передача оператору

### 2. Код (двойная защита):
- **communicative_scripts_service.py:164** - защита в get_fallback_message
- **main_agent.py:3418** - защита в _generate_ai_question

---

## Как протестировать

### Способ 1: Через Telegram бота (простой)

1. **Запустите бота:**
   ```bash
   systemctl status gunicorn-komunal-dom
   ```

2. **Откройте Telegram бота** @KomunalkaProblemBot

3. **Начните диалог абсурдными сообщениями** (чтобы бот не мог определить услугу):

   ```
   Вы: привет
   Бот: [вопрос 1]
   Вы: абракадабра
   Бот: [вопрос 2]
   Вы: фырфырфыр
   Бот: [вопрос 3]
   Вы: бла бла бла
   Бот: [вопрос 4]
   Вы: ёклмн
   Бот: [вопрос 5]
   Вы: хз что
   Бот: [вопрос 6]
   Вы: еще раз
   Бот: К сожалению, я не смог определить вашу проблему. Пожалуйста, свяжитесь с оператором по телефону.
   ```

4. **Ожидаемый результат:**
   - Ходы 1-6: разные уточняющие вопросы
   - Ход 7+: финальное сообщение о передаче оператору
   - **НЕ должно быть бесконечных повторов**

### Способ 2: Через тестовый симулятор (детальный)

1. **Запустите тестовый бот:**
   ```bash
   cd /var/www/komunal-dom_ru
   source venv/bin/activate
   python test_bot_simulator.py
   ```

2. **Используйте сценарий для теста:**
   - Создайте файл `test_loop.py`:
   ```python
   import asyncio
   from main_agent import MainAgent

   async def test_anti_loop():
       agent = MainAgent()
       session_id = "test_loop_20260121"

       # Отправляем абсурдные сообщения 10 раз подряд
       messages = [
           "привет",
           "абракадабра",
           "фырфыр",
           "бла бла бла",
           "ёклмн",
           "хз что",
           "еще раз",
           "не знаю",
           "чтото",
           "ну"
       ]

       for i, msg in enumerate(messages, 1):
           print(f"\n=== ХОД {i} ===")
           print(f"Пользователь: {msg}")

           result = await agent.process_message(
               message_text=msg,
               session_id=session_id,
               channel='test_bot'
           )

           print(f"Бот: {result.get('message', '?')[:100]}")

           if i >= 7:
               # После 7 хода должно быть финальное сообщение
               if "оператор" in result.get('message', '').lower():
                   print("✅ ЗАЩИТА РАБОТАЕТ!")
               else:
                   print("❌ ЗАЩИТА НЕ РАБОТАЕТ!")

   asyncio.run(test_anti_loop())
   ```

3. **Запустите тест:**
   ```bash
   python test_loop.py
   ```

---

## Как проверить логи

### 1. Логи gunicorn (реальные диалоги):
```bash
journalctl -u gunicorn-komunal-dom -f | grep -E "ANTI-LOOP|fallback"
```

**Ожидаемые сообщения при срабатывании защиты:**
```
[ANTI-LOOP] Слишком много AI-вопросов (turn=7) -> возвращаем финальное сообщение
[ANTI-LOOP] Слишком много fallback сообщений (turn=7) -> возвращаем финальное сообщение
```

### 2. Проверка в БД (история сообщений):
```bash
source .env
PGPASSWORD="$DB_PASSWORD" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "
SELECT session_id, timestamp, direction, message_content
FROM dialog_logs
WHERE session_id = 'ВАШ_SESSION_ID'
ORDER BY timestamp
LIMIT 20;"
```

---

## Если бот все равно зацикливается

### Сбор трассировки для отладки

1. **Найдите session_id проблемного диалога:**
   ```bash
   # Из логов gunicorn
   journalctl -u gunicorn-komunal-dom --since "5 minutes ago" | grep "session_id"
   ```

2. **Сгенерируйте трассировку:**
   ```bash
   cd /var/www/komunal-dom_ru
   source venv/bin/activate

   # Замените telegram_123456 на ваш session_id
   python trace_report_service.py telegram_123456
   ```

3. **Файл трассировки будет создан:**
   ```
   /tmp/_tras_diag_ГГГГММДД_ЧЧММСС.md
   ```

4. **Отправьте мне:**
   - Файл трассировки
   - Логи gunicorn за период зацикливания:
     ```bash
     journalctl -u gunicorn-komunal-dom --since "10 minutes ago" > /tmp/gunicorn_loop.log
     ```

---

## Критерии успеха

✅ **Защита работает:**
- После 6 ходов бот отправляет финальное сообщение
- В логах есть `[ANTI-LOOP]`
- Нет бесконечных повторов

❌ **Защита не работает:**
- Бот повторяет один и тот же вопрос >7 раз
- Нет логов `[ANTI-LOOP]`
- В трассировке видно, что `dialog_turn` растет без проверки

---

## Дополнительная проверка

### Проверка скриптов в БД:
```bash
source .env
PGPASSWORD="$DB_PASSWORD" psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "
SELECT script_name, min_dialog_turn, max_dialog_turn
FROM message_handler_communicativescript
WHERE script_type = 'fallback'
ORDER BY min_dialog_turn;"
```

**Ожидаемый результат:**
```
fallback_no_candidates     | 1 | 3
fallback_followup_clarify  | 2 | 5
fallback_clarify_location  | 2 | 5
fallback_clarify_object    | 3 | 5
fallback_clarify_details   | 4 | 5
fallback_final_operator    | 6 | -1  <-- с 6 хода
```

---

## Коммиты с исправлениями

- `1499951` - Защита в communicative_scripts_service.py + миграция БД
- `75cd7bc` - Защита в main_agent.py (_generate_ai_question)

Ветка: `feature/tz-26-12-critical-fixes`

---

**В случае проблем:** отправьте трассировку и логи gunicorn за период зацикливания.
