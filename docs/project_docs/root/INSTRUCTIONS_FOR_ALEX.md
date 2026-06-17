# ИНСТРУКЦИЯ ДЛЯ ALEX - Подключение и настройка

## ДОСТУПЫ К СИСТЕМЕ

| Параметр | Значение |
|---|---|
| **Сервер** | komunal-dom.ru (IP: нужно узнать у администратора) |
| **SSH порт** | 22 |
| **Пользователь** | alex |
| **Пароль** | AlexRoot2026= |
| **Home директория** | /home/alex |
| **Проект** | /var/www/komunal-dom_ru |

## ДОСТУПЫ К DJANGO

| Параметр | Значение |
|---|---|
| **URL админки** | http://komunal-dom.ru/admin/ |
| **Пользователь Django** | alex |
| **Пароль Django** | AlexRoot2026= |
| **Роль** | Администратор Django (полный доступ) |

## ДОСТУПЫ К POSTGRESQL

| Параметр | Значение |
|---|---|
| **Хост** | localhost |
| **Порт** | 5432 |
| **База данных** | aspect_objects_db |
| **Пользователь БД** | aspect_alex |
| **Пароль БД** | AlexRoot2026= |
| **Права** | SELECT на все таблицы |

---

# ПОДКЛЮЧЕНИЕ ЧЕРЕЗ PUTTY

## Шаг 1. Скачивание PuTTY

1. Перейдите на https://www.putty.org/
2. Скачайте и установите PuTTY (включая PuTTYgen)

## Шаг 2. Создание SSH ключей

### Генерация ключевой пары:

1. **Запустите PuTTYgen**
   - Пуск → Программы → PuTTY → PuTTYgen

2. **Настройте параметры ключа:**
   - Параметр: RSA
   - Биты: 4096 (рекомендуется)
   - Нажмите **Generate**

3. **Двигайте мышкой** для генерации случайных чисел

4. **Сохраните приватный ключ:**
   - Нажмите **Save private key**
   - Сохраните как `C:\Users\YourName\.ssh\komunal-dom-alex.ppk`
   - **ВАЖНО:** Никому не передавайте этот файл!

5. **Скопируйте публичный ключ:**
   - Текст из окна "Public key for pasting..."
   - Сохраните в файл `komunal-dom-alex.pub`

## Шаг 3. Добавление публичного ключа на сервер

### Способ 1: Через PuTTY (с паролем)

1. **Настройте соединение в PuTTY:**
   - Host Name: `alex@komunal-dom.ru`
   - Port: 22
   - Connection Type: SSH

2. **Подключитесь:**
   - Нажмите **Open**
   - Введите пароль: `AlexRoot2026=`

3. **Добавьте публичный ключ на сервер:**
   ```bash
   mkdir -p ~/.ssh
   chmod 700 ~/.ssh
   nano ~/.ssh/authorized_keys
   ```

4. **Вставьте публичный ключ** (из окна PuTTYgen):
   - Вставьте весь текст из "Public key for pasting..."
   - Сохраните: Ctrl+O, Enter, Ctrl+X

5. **Установите правильные права:**
   ```bash
   chmod 600 ~/.ssh/authorized_keys
   ```

## Шаг 4. Настройка PuTTY для ключевой аутентификации

1. **Откройте PuTTY**

2. **Создайте сохраненную сессию:**
   - Host Name: `alex@komunal-dom.ru`
   - Port: 22
   - Saved Sessions: `KomunalDom-Alex`

3. **Настройте приватный ключ:**
   - Меню: Connection → SSH → Auth
   - Поле "Private key file for authentication":
     - Нажмите **Browse**
     - Выберите файл `komunal-dom-alex.ppk`

4. **Сохраните сессию:**
   - Вернитесь в **Session**
   - Нажмите **Save**

5. **Проверьте подключение:**
   - Выберите сессию "KomunalDom-Alex"
   - Нажмите **Open**
   - **УСПЕХ:** Вы войдете БЕЗ пароля!

---

# РАБОТА С GIT И ПРОЕКТОМ

## Первичная настройка Git

После первого подключения выполните:

```bash
# Настройка вашего Git пользователя (для коммитов от Alex)
git config --global user.name "Alex"
git config --global user.email "alex@komunal-dom.ru"

# Проверка
git config --global user.name
git config --global user.email
```

## Переход в директорию проекта

```bash
cd /var/www/komunal-dom_ru
```

## Проверка Git статуса

```bash
git status
```

## Создание feature-ветки

```bash
git checkout main
git pull origin main
git checkout -b feature/название-задачи
```

## Коммит изменений

```bash
git status                                      # Проверить, что изменилось
git add имя_файла.py                            # Добавить файл
git commit -m "Описание изменения"             # Закоммитить
git push                                        # Отправить на GitHub
```

---

# ПЕРЕКЛЮЧЕНИЕ МЕЖДУ ПОЛЬЗОВАТЕЛЯМИ

## Работа от имени Olga

```bash
su - olga
cd /var/www/komunal-dom_ru
git config --global user.name "Olga"
git config --global user.email "olga@komunal-dom.ru"
```

## Работа от имени root

```bash
sudo -i
cd /var/www/komunal-dom_ru
git config --global user.name "root"
git config --global user.email "root@komunal-dom.ru"
```

## Возврат к Alex

```bash
exit
git config --global user.name "Alex"
git config --global user.email "alex@komunal-dom.ru"
```

---

# ПОЛЕЗНЫЕ КОМАНДЫ

## Управление сервисами

```bash
# Перезапуск gunicorn
sudo systemctl restart gunicorn-komunal-dom

# Проверка статуса
sudo systemctl status gunicorn-komunal-dom

# Перезагрузка nginx
sudo systemctl reload nginx
```

## Работа с Django

```bash
cd /var/www/komunal-dom_ru
source venv/bin/activate

# Запуск сервера (для разработки)
./manage.sh run

# Миграции
./manage.sh migrate

# Django shell
./manage.sh shell

# Создание суперпользователя
./manage.sh createsuperuser
```

## PostgreSQL запросы

```bash
PGPASSWORD="AlexRoot2026=" psql -h localhost -U aspect_alex -d aspect_objects_db -c "SELECT * FROM services_catalog LIMIT 10;"
```

---

# ПРОВЕРКА ДОСТУПОВ

После подключения выполните проверку:

```bash
# 1. Проверка пользователя
whoami
# Ожидается: alex

# 2. Проверка групп
groups
# Ожидается: alex sudo www-data

# 3. Проверка прав на проект
ls -la /var/www/komunal-dom_ru | head -5
# Ожидается: drwxrwsr-x (группа www-data имеет права записи)

# 4. Проверка Git
cd /var/www/komunal-dom_ru && git config --global user.name
# Ожидается: Alex

# 5. Проверка PostgreSQL
PGPASSWORD="AlexRoot2026=" psql -h localhost -U aspect_alex -d aspect_objects_db -c "SELECT current_user;"
# Ожидается: aspect_alex

# 6. Проверка Django (через shell)
/var/www/komunal-dom_ru/venv/bin/python /var/www/komunal-dom_ru/manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print(User.objects.filter(username='alex').exists())"
# Ожидается: True
```

---

# СВОДНАЯ ТАБЛИЦА ДОСТУПОВ

| Система | Пользователь | Пароль | Права |
|---|---|---|---|
| **Linux (SSH)** | alex | AlexRoot2026= | sudo, www-data |
| **Django Admin** | alex | AlexRoot2026= | Администратор Django |
| **PostgreSQL** | aspect_alex | AlexRoot2026= | SELECT на все таблицы |
| **GitHub/Git** | Alex | - | Коммиты от Alex |

---

# ОШИБКИ И РЕШЕНИЯ

## Ошибка: Permission denied

```bash
# Если нет прав на запись в файлы проекта
sudo chown -R :www-data /var/www/komunal-dom_ru
sudo chmod -R 775 /var/www/komunal-dom_ru
```

## Ошибка: Git не отправляет коммиты

```bash
# Проверьте, от какого пользователя вы коммитите
git log -1 --format="%an <%ae>"
# Должно быть: Alex <alex@komunal-dom.ru>
```

## Ошибка: Django не видит пользователя

```bash
# Проверьте, что пользователь существует
/var/www/komunal-dom_ru/venv/bin/python /var/www/komunal-dom_ru/manage.py shell -c "from django.contrib.auth import get_user_model; User = get_user_model(); print(list(User.objects.filter(username='alex').values()))"
```

---

# КОНТАКТЫ

При возникновении проблем обращайтесь к:
- Администратор сервера: Olga (olga@komunal-dom.ru)
- Документация проекта: /var/www/komunal-dom_ru/CLAUDE.md

---

**Дата создания:** 2026-03-10
**Создал:** Claude (от имени root)
