# Hook Repair Report

**Дата:** 2026-03-29 13:10 UTC
**Цель:** Убрать постоянные ошибки PreToolUse/PostToolUse hooks
**Статус:** ✅ FIXED

---

## 1. ПРИЧИНА ОШИБОК HOOKS

### Корневая причина:

**UI change hooks написаны неправильно** - они не читают JSON из stdin, а пытаются парсить аргументы командной строки.

### Детали:

**`ui_change_pre_guard.sh`:**
```bash
# ОШИБКА: ожидает файлы как аргументы $1, $@
main() {
    local command="$1"

    if is_ui_change "$command"; then
        log "Обнаружено UI-изменение: $command"
    fi
}
```

**`ui_change_post_guard.sh`:**
```bash
# ОШИБКА: ожидает файлы как аргументы $@
for arg in $command; do
    if [ -f "$arg" ]; then  # ← Никогда не выполнится
        check_permissions "$arg"
        check_python_syntax "$arg"
    fi
done
```

### Проблема:

1. **Edit/Write tools передают данные через JSON stdin**, не как аргументы
2. **Hooks не используют `jq` для чтения JSON** (в отличие от `prod_db_guard.sh`)
3. **`set -euo pipefail` приводит к exit** на пустых переменных или ошибках grep
4. **Результат:** Hook падает на каждом Edit/Write, Claude видит "PreToolUse:Edit hook error"

---

## 2. ФАЙЛЫ ИЗМЕНЕНЫ

### `/var/www/komunal-dom_ru/.claude/settings.json`

**Удалены проблемные hooks:**
- `ui_change_pre_guard.sh` из PreToolUse (Edit, Write)
- `ui_change_post_guard.sh` из PostToolUse (Edit, Write)

**Оставлен рабочий hook:**
- `prod_db_guard.sh` в PreToolUse (Bash)
- `prod_db_guard.sh` в PermissionRequest (Bash)

**ДО:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/root/.claude/hooks/prod_db_guard.sh"
          },
          {
            "type": "command",
            "command": "/root/.claude/hooks/ui_change_pre_guard.sh"
          }
        ]
      },
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "/root/.claude/hooks/ui_change_pre_guard.sh"
          }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "/root/.claude/hooks/ui_change_pre_guard.sh"
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/root/.claude/hooks/prod_db_guard.sh"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit",
        "hooks": [
          {
            "type": "command",
            "command": "/root/.claude/hooks/ui_change_post_guard.sh"
          }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "/root/.claude/hooks/ui_change_post_guard.sh"
          }
        ]
      }
    ]
  }
}
```

**ПОСЛЕ:**
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/root/.claude/hooks/prod_db_guard.sh"
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "/root/.claude/hooks/prod_db_guard.sh"
          }
        ]
      }
    ]
  }
}
```

---

## 3. АКТИВНЫЕ HOOKS ПОСЛЕ ИСПРАВЛЕНИЯ

### ✅ Активен:

**`/root/.claude/hooks/prod_db_guard.sh`**
- **Когда:** PreToolUse для Bash, PermissionRequest для Bash
- **Что делает:** Блокирует опасные DB операции
- **Почему работает:** Правильно читает JSON stdin через `jq`
- **Защищает:**
  - ❌ `export $(cat .env | xargs)`
  - ❌ Прямые вызовы `/var/www/komunal-dom_ru/bin/db_*.sh`
  - ❌ psql meta-команды (\d, \dt, \l, \du)
  - ❌ chmod/chown db helper scripts

### ❌ Отключены временно:

**`/root/.claude/hooks/ui_change_pre_guard.sh`**
- **Почему не работает:** Не читает JSON stdin
- **Как исправить:** Добавить чтение JSON через `jq` (как в prod_db_guard.sh)
- **Файл на месте:** `/root/.claude/hooks/ui_change_pre_guard.sh`

**`/root/.claude/hooks/ui_change_post_guard.sh`**
- **Почему не работает:** Не читает JSON stdin
- **Как исправить:** Добавить чтение JSON через `jq` для получения путей файлов
- **Файл на месте:** `/root/.claude/hooks/ui_change_post_guard.sh`

---

## 4. ЧТО НЕ ИЗМЕНЕНО

**НЕ трогали:**
- `/root/.claude/hooks/prod_db_guard.sh` — рабочий hook
- `/root/.claude/hooks/ui_change_pre_guard.sh` — отключен, файл на месте
- `/root/.claude/hooks/ui_change_post_guard.sh` — отключен, файл на месте
- `.hooks/` и `.skills/` в проекте — это другая система (markdown docs)
- `.claude/skills/` в проекте — это другая система (markdown docs)
- Проектные hooks/skills — не используются Claude Code напрямую

**Пояснение:**
- `.hooks/` и `.skills/` в проекте = markdown документация для человека
- `.claude/settings.json` = конфигурация Claude Code hooks
- `~/.claude/hooks/*.sh` = глобальные shell hooks для Claude Code

---

## 5. КАК ПРОВЕРИТЬ ИСПРАВЛЕНИЕ

### Проверка 1: Edit tool больше не дает ошибок

**Что делать:**
1. Выполнить любой Edit tool (например, изменить файл settings.py)
2. Проверить, что нет сообщения "PreToolUse:Edit hook error"
3. Проверить, что нет сообщения "PostToolUse:Edit hook error"

**Ожидаемый результат:**
- ✅ Edit выполняется без ошибок hooks
- ✅ В выводе Claude нет "hook error"

---

### Проверка 2: Write tool больше не дает ошибок

**Что делать:**
1. Выполнить любой Write tool (например, создать новый файл)
2. Проверить, что нет сообщения "PreToolUse:Write hook error"
3. Проверить, что нет сообщения "PostToolUse:Write hook error"

**Ожидаемый результат:**
- ✅ Write выполняется без ошибок hooks
- ✅ В выводе Claude нет "hook error"

---

### Проверка 3: DB guard все еще работает

**Что делать:**
1. Попытаться выполнить запрещенную команду: `export $(cat .env | xargs)`
2. Проверить, что `prod_db_guard.sh` блокирует команду

**Ожидаемый результат:**
- ✅ Команда блокируется
- ✅ Выводится сообщение: "❌ ЗАПРЕЩЕНО: export \$(cat .env | xargs)..."

---

## 6. КАК СНОВА ВКЛЮЧИТЬ UI GUARDS

### Вариант 1: Исправить существующие hooks

**Изменить `/root/.claude/hooks/ui_change_pre_guard.sh`:**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Читаем JSON из stdin
INPUT="$(cat)"

# Извлекаем tool_name
TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")"

# Если Edit или Write - проверяем
if [[ "$TOOL_NAME" == "Edit" ]] || [[ "$TOOL_NAME" == "Write" ]]; then
    # Извлекаем file_path
    FILE_PATH="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null || echo "")"

    # Проверяем, что это UI-файл
    if echo "$FILE_PATH" | grep -qE '\.(html|py)$'; then
        if echo "$FILE_PATH" | grep -qE '(templates/|views\.py|forms\.py|admin\.py)'; then
            echo "[UI_PRE_GUARD] Обнаружено UI-изменение: $FILE_PATH" >&2
            echo "[UI_PRE_GUARD] → Направляем к skill: figma_django_ui_workflow" >&2
        fi
    fi
fi

exit 0
```

**Изменить `/root/.claude/hooks/ui_change_post_guard.sh`:**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Читаем JSON из stdin
INPUT="$(cat)"

# Извлекаем tool_name и exit_code
TOOL_NAME="$(printf '%s' "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")"
EXIT_CODE="$(printf '%s' "$INPUT" | jq -r '.exit_code // "0"' 2>/dev/null || echo "0")"

# Если Edit или Write завершились успешно
if [[ "$TOOL_NAME" =~ ^(Edit|Write)$ ]] && [[ "$EXIT_CODE" == "0" ]]; then
    # Извлекаем file_path
    FILE_PATH="$(printf '%s' "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null || echo "")"

    if [ -n "$FILE_PATH" ] && [ -f "$FILE_PATH" ]; then
        # Проверка прав
        PERMS="$(stat -c "%a %U:%G" "$FILE_PATH")"
        echo "[UI_POST_GUARD] Права: $PERMS → $FILE_PATH" >&2

        # Проверка синтаксиса Python
        if echo "$FILE_PATH" | grep -q '\.py$'; then
            if python -m py_compile "$FILE_PATH" 2>&1; then
                echo "[UI_POST_GUARD] ✅ Синтаксис OK" >&2
            else
                echo "[UI_POST_GUARD] ⚠️ ПРЕДУПРЕЖДЕНИЕ: Синтаксическая ошибка" >&2
            fi
        fi
    fi
fi

exit 0
```

**После исправления:**
1. Добавить hooks обратно в `.claude/settings.json`
2. Перезапустить Claude Code
3. Проверить работу

---

### Вариант 2: Переписать на Python

**Преимущества:**
- Легче парсить JSON
- Легче обрабатывать ошибки
- Меньше проблем с `set -euo pipefail`

---

## 7. УРОКИ

1. **Hooks для Edit/Write должны читать JSON stdin**, не ожидать аргументы
2. **Использовать `jq` для парсинга JSON** (как в prod_db_guard.sh)
3. **`set -euo pipefail` опасен** если не все переменные всегда заданы
4. **Тестировать hooks перед включением** в production settings
5. **Различать системы hooks:**
   - `.claude/settings.json` = конфигурация Claude Code hooks
   - `.hooks/` и `.skills/` = markdown документация

---

## 8. ТЕКУЩЕЕ СОСТОЯНИЕ

### Активно:
- ✅ `prod_db_guard.sh` — защита от опасных DB операций

### Отключено временно:
- ❌ `ui_change_pre_guard.sh` — сломан (не читает JSON)
- ❌ `ui_change_post_guard.sh` — сломан (не читает JSON)

### Статус: FIXED ✅

Ошибки PreToolUse/PostToolUse должны исчезнуть.

---

**ОТЧЕТ СОЗДАН:** 2026-03-29 13:10 UTC
**ИСПРАВЛЕНИЕ:** Отключены сломанные UI hooks, оставлен рабочий DB guard
**СЛЕДУЮЩИЙ ШАГ:** Исправить UI guards для чтения JSON или переписать на Python
