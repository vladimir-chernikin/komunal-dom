# Инструкция для Olga по работе с Claude Code

## Быстрый старт

### 1. Подключение к серверу

```bash
ssh olga@komunal-dom.ru
```

### 2. Переход в папку проекта

```bash
cdp
```
(алиас для быстрого перехода в /var/www/komunal-dom_ru)

Или вручную:
```bash
cd /var/www/komunal-dom_ru
```

### 3. Запуск Claude Code

```bash
claude
```

## Проверка доступа

После входа на сервер проверьте что всё работает:

```bash
# Проверка Claude
claude --version

# Проверка npm/npx
npm --version
npx --version

# Проверка coding-helper
npx @z_ai/coding-helper --version

# Проверка доступа к проекту
ls -la

# Проверка прав на запись
touch test.tmp && rm test.tmp
```

## Вашы права

- **Чтение:** все файлы проекта
- **Запись:** все файлы проекта
- **Git:** push/pull от вашего имени
- **Sudo:** административные команды
- **npm/npx:** установка пакетов Node.js

## Coding Tool Helper (@z_ai/coding-helper)

Доступен через npx для управления API ключами и настройками.

### Основные команды:

```bash
# Интерактивное меню
npx @z_ai/coding-helper

# Инициализация
npx @z_ai/coding-helper init

# Управление API ключами
npx @z_ai/coding-helper auth

# Проверка работоспособности
npx @z_ai/coding-helper doctor

# Настройка языка
npx @z_ai/coding-helper lang show
npx @z_ai/coding-helper lang set zh_CN
```

### Подробная справка:

```bash
npx @z_ai/coding-helper --help
```

## Рабочий процесс

1. **Обновить main:**
   ```bash
   git checkout main
   git pull origin main
   ```

2. **Создать ветку:**
   ```bash
   git checkout -b feature/описание
   ```

3. **Внести изменения:**
   - Используйте Claude для редактирования файлов
   - Тестируйте изменения

4. **Запушить:**
   ```bash
   git add .
   git commit -m "Описание изменений"
   git push origin feature/описание
   ```

5. **Создать Pull Request на GitHub**

## Полезные команды

```bash
# Статус git
git status

# Текущая ветка
git branch

# История коммитов
git log --oneline

# Дифф изменений
git diff
```

## Проблемы?

Если Claude не работает:

```bash
# Проверить версию
claude --version

# Проверить путь
which claude

# Должно быть: /usr/local/bin/claude
```

Если нет доступа к файлам:

```bash
# Проверить права
ls -la

# Должны быть: olga www-data
```

Если npx или coding-helper не работают:

```bash
# Проверить npm
npm --version

# Проверить npx
npx --version

# Проверить coding-helper
npx @z_ai/coding-helper --version

# Если не работает, переустановите:
npm install -g @z_ai/coding-helper
```

## Контакты

- **GitHub:** https://github.com/vladimir-chernikin/komunal-dom
- **Проект:** /var/www/komunal-dom_ru
