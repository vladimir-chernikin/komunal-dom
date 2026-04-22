# ИНСТРУКЦИЯ ПО НАСТРОЙКЕ GIT ДЛЯ РАЗНЫХ ПОЛЬЗОВАТЕЛЕЙ

## ПРОБЛЕМА

В репозитории была локальная конфигурация Git с пользователем Olga, из-за чего **ВСЕ коммиты** шли от её имени, независимо от того, кто выполнял коммит (root, Alex).

**Причина:** В файле `.git/config` была запись:
```
[user]
    name = Olga
    email = olga@komunal-dom.ru
```

**Решение:** Локальная конфигурация Git удалена, теперь используется **глобальная конфигурация** каждого пользователя.

---

## НАСТРОЙКА GIT ДЛЯ РАЗНЫХ ПОЛЬЗОВАТЕЛЕЙ

### 1. Alex (при работе от имени Alex)

```bash
# Настройка Git для Alex
git config --global user.name "Alex"
git config --global user.email "alex@komunal-dom.ru"

# Проверка
git config --global user.name
git config --global user.email
```

**Результат:** Все коммиты от Alex будут подписаны как `Alex <alex@komunal-dom.ru>`

---

### 2. Olga (при работе от имени Olga)

```bash
# Настройка Git для Olga
git config --global user.name "Olga"
git config --global user.email "olga@komunal-dom.ru"

# Проверка
git config --global user.name
git config --global user.email
```

**Результат:** Все коммиты от Olga будут подписаны как `Olga <olga@komunal-dom.ru>`

---

### 3. root (при работе от имени root)

```bash
# Настройка Git для root
git config --global user.name "root"
git config --global user.email "root@komunal-dom.ru"

# Проверка
git config --global user.name
git config --global user.email
```

**Результат:** Все коммиты от root будут подписаны как `root <root@komunal-dom.ru>`

---

## ПРОВЕРКА АВТОРА КОММИТА

Перед каждым коммитом проверяйте, от чьего имени он будет сделан:

```bash
# Проверить текущего пользователя Git
git config user.name
git config user.email

# Или посмотреть последний коммит
git log -1 --format="%an <%ae>"
```

**Ожидаемый результат:**
- Если работаете как Alex → `Alex <alex@komunal-dom.ru>`
- Если работаете как Olga → `Olga <olga@komunal-dom.ru>`
- Если работаете как root → `root <root@komunal-dom.ru>`

---

## ПЕРЕКЛЮЧЕНИЕ МЕЖДУ ПОЛЬЗОВАТЕЛЯМИ

### Переключиться на Olga

```bash
# Войти как Olga
su - olga
cd /var/www/komunal-dom_ru

# Настроить Git (если еще не настроен)
git config --global user.name "Olga"
git config --global user.email "olga@komunal-dom.ru"

# Проверить
git config --global user.name
```

### Переключиться на Alex

```bash
# Войти как Alex
su - alex
cd /var/www/komunal-dom_ru

# Настроить Git (если еще не настроен)
git config --global user.name "Alex"
git config --global user.email "alex@komunal-dom.ru"

# Проверить
git config --global user.name
```

### Переключиться на root

```bash
# Войти как root (если не root)
sudo -i

# Настроить Git (если еще не настроен)
git config --global user.name "root"
git config --global user.email "root@komunal-dom.ru"

# Проверить
git config --global user.name
```

---

## СТАНДАРТНЫЙ РАБОЧИЙ ПРОЦЕСС

### 1. Alex делает коммит

```bash
# Убедиться, что вы Alex
whoami  # Должно быть: alex

# Перейти в проект
cd /var/www/komunal-dom_ru

# Проверить Git конфигурацию
git config user.name  # Должно быть: Alex

# Если не Alex, настроить:
git config --global user.name "Alex"
git config --global user.email "alex@komunal-dom.ru"

# Работа с проектом...
git add .
git commit -m "Описание изменений"
git push
```

### 2. root делает коммит

```bash
# Убедиться, что вы root
whoami  # Должно быть: root

# Перейти в проект
cd /var/www/komunal-dom_ru

# Проверить Git конфигурацию
git config user.name  # Должно быть: root

# Если не root, настроить:
git config --global user.name "root"
git config --global user.email "root@komunal-dom.ru"

# Работа с проектом...
git add .
git commit -m "Описание изменений"
git push
```

### 3. Olga делает коммит

```bash
# Убедиться, что вы Olga
whoami  # Должно быть: olga

# Перейти в проект
cd /var/www/komunal-dom_ru

# Проверить Git конфигурацию
git config user.name  # Должно быть: Olga

# Если не Olga, настроить:
git config --global user.name "Olga"
git config --global user.email "olga@komunal-dom.ru"

# Работа с проектом...
git add .
git commit -m "Описание изменений"
git push
```

---

## АВТОМАТИЗАЦИЯ (ДОПОЛНИТЕЛЬНО)

### Добавить в .bashrc для автоматической настройки

Для **Alex** (`/home/alex/.bashrc`):
```bash
# Автоматическая настройка Git для Alex
if [ -f "/var/www/komunal-dom_ru/.git/config" ]; then
    cd /var/www/komunal-dom_ru 2>/dev/null
    if [ "$(git config --global user.name)" != "Alex" ]; then
        git config --global user.name "Alex"
        git config --global user.email "alex@komunal-dom.ru"
    fi
fi
```

Для **root** (`/root/.bashrc`):
```bash
# Автоматическая настройка Git для root
if [ -f "/var/www/komunal-dom_ru/.git/config" ]; then
    cd /var/www/komunal-dom_ru 2>/dev/null
    if [ "$(git config --global user.name)" != "root" ]; then
        git config --global user.name "root"
        git config --global user.email "root@komunal-dom.ru"
    fi
fi
```

Для **Olga** (`/home/olga/.bashrc`):
```bash
# Автоматическая настройка Git для Olga
if [ -f "/var/www/komunal-dom_ru/.git/config" ]; then
    cd /var/www/komunal-dom_ru 2>/dev/null
    if [ "$(git config --global user.name)" != "Olga" ]; then
        git config --global user.name "Olga"
        git config --global user.email "olga@komunal-dom.ru"
    fi
fi
```

---

## ПРОВЕРКА ИСТОРИИ КОММИТОВ

```bash
# Посмотреть последние 10 коммитов с авторами
git log -10 --format="%h | %an | %ae | %s"

# Или более подробно
git log --pretty=format:"%h - %an (%ae): %s" -10
```

**Ожидается:**
- Коммиты от Alex помечены как `Alex <alex@komunal-dom.ru>`
- Коммиты от Olga помечены как `Olga <olga@komunal-dom.ru>`
- Коммиты от root помечены как `root <root@komunal-dom.ru>`

---

## ТЕКУЩАЯ СИТУАЦИЯ (2026-03-10)

✅ **Исправлено:**
- Локальная конфигурация Git (Olga) удалена из `.git/config`
- Глобальная конфигурация настроена для root
- Создан тестовый коммит от root: `b606bd5 | root | root@komunal-dom.ru`

⚠️ **Старые коммиты:**
- Все коммиты до `b606bd5` помечены как `Olga` (это нормально, так как была локальная конфигурация)

✅ **Новые коммиты:**
- Теперь каждый пользователь должен настроить глобальную конфигурацию Git
- Коммиты будут корректно помечаться автором

---

## КРИТИЧЕСКИ ВАЖНО

**ПЕРЕД КАЖДЫМ КОММИТОМ ПРОВЕРЯЙТЕ:**

```bash
git config user.name   # Текущий пользователь Git
whoami                  # Текущий пользователь системы
```

**Если они не соответствуют - НАСТРОЙТЕ GIT!**

---

**Дата создания:** 2026-03-10
**Создал:** Claude (от имени root)
