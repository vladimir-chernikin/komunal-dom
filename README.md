# Komunal-Dom - Управляющая компания Аспект

AI-диспетчер для Telegram и Web на базе Django + YandexGPT

## Стек технологий

- **Backend:** Django 6.0, Python 3.12
- **Database:** PostgreSQL 16
- **Web Server:** nginx + gunicorn
- **AI:** YandexGPT API
- **Bot:** python-telegram-bot

## Быстрый старт

### 1. Клонирование репозитория

```bash
git clone https://github.com/vladimir-chernikin/komunal-dom.git
cd komunal-dom
```

### 2. Настройка окружения

```bash
# Создание виртуального окружения
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
pip install -r requirements.txt
```

### 3. Конфигурация

Скопируйте `.env.example` в `.env` и заполните реальные значения:

```bash
cp .env.example .env
nano .env
```

### 4. Миграции базы данных

```bash
python manage.py migrate
```

### 5. Создание суперпользователя

```bash
python manage.py createsuperuser
```

### 6. Запуск сервера

```bash
./manage.sh run
```

## Совместная разработка

### Ветвление (Branching)

1. Создайте ветку для новой задачи:
```bash
git checkout -b feature/название-фичи
```

2. Вносите изменения, коммитите:
```bash
git add .
git commit -m "Описание изменений"
```

3. Отправляйте ветку в GitHub:
```bash
git push origin feature/название-фичи
```

4. Создавайте Pull Request на GitHub

### Стандартные ветки

- `main` - основная ветка (production-ready код)
- `develop` - ветка разработки
- `feature/*` - ветки для новых фич
- `bugfix/*` - ветки для исправления багов
- `hotfix/*` - ветки для срочных исправлений на production

## Структура проекта

```
komunal-dom/
├── komunal_dom/          # Основной проект Django
├── portal/               # Приложение портала УК
├── kladr/                # Приложение КЛАДР
├── file_manager/         # Файловый менеджер
├── message_handler/      # Обработчик сообщений AI
├── venv/                 # Виртуальное окружение
├── media/                # Медиа файлы
├── static/               # Статические файлы
└── manage.py             # Управление Django
```

## Микросервисы AI

- **MainAgent** - главный координатор воронки точности
- **TagSearchService** - нечеткий поиск по тегам
- **SemanticSearchService** - логико-семантический поиск
- **VectorSearchService** - семантический поиск по векторной базе
- **AIAgentService** - поиск с помощью YandexGPT

## Тестирование

```bash
# Запуск тестового бота
python test_bot_simulator.py

# Запуск всех тестов
python manage.py test

# Диагностика диалога
python dialog_trace_service.py --session-id <session_id>
```

## Лицензия

Proprietary - Управляющая компания Аспект

## Контакты

- GitHub: https://github.com/vladimir-chernikin/komunal-dom
- Сайт: https://komunal-dom.ru
