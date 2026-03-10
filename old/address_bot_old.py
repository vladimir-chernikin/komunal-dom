#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram бот для проверки адресов и обработки заявок УК "Аспект"
РЕФАКТОРЕННАЯ ВЕРСИЯ - использует новую систему AI
"""

import asyncio
import logging
import os
import re
import sys
import html
import uuid
from decouple import config

# Telegram imports
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Django setup
sys.path.append('/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

# Импортируем новую рефакторенную систему
from service_detection_orchestrator import ServiceDetectionOrchestrator
from dialog_memory_manager import DialogMemoryManager

# Настройки
TELEGRAM_TOKEN = config('TELEGRAM_TOKEN')
YANDEX_API_KEY = config('YANDEX_API_KEY')
YANDEX_FOLDER_ID = config('YANDEX_FOLDER_ID')

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Список ругательств и нецензурных слов для фильтрации
PROFANE_WORDS = [
    'хуй', 'пизд', 'бляд', 'еба', 'сук', 'сукін', 'блять', 'говно',
    'жопа', 'муда', 'хер', 'падл', 'урод', 'сволоч', 'дебил',
    'дур', 'туп', 'лох', 'придур', 'козёл', 'козел'
]

class ConversationState:
    """Класс для хранения состояния диалога с пользователем"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.address_attempts = 0
        self.last_address = None
        self.warnings_count = 0
        self.last_question_time = None

class AddressCheckerBot:
    """Бот для проверки адресов с AI промптами из БД"""

    def __init__(self):
        self.bot_name = "Сигизмунд Лазоревич"
        self.use_yandex = True
        self.yandex_api_key = YANDEX_API_KEY
        self.yandex_folder_id = YANDEX_FOLDER_ID

        # Хранилище состояний диалогов
        self.conversations = {}

    def get_conversation_state(self, user_id):
        """Получить или создать состояние диалога"""
        if user_id not in self.conversations:
            self.conversations[user_id] = ConversationState(user_id)
        return self.conversations[user_id]

    def contains_profanity(self, text):
        """Проверка на наличие ругательств в тексте"""
        text_lower = text.lower()
        for word in PROFANE_WORDS:
            if word in text_lower:
                return True
        return False

    async def ask_yandexgpt(self, prompt, max_tokens=300):
        """Запрос к YandexGPT API с системным промптом из БД"""
        if not self.use_yandex:
            return None

        try:
            import requests
            import json

            url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
            headers = {
                "Authorization": f"Api-Key {self.yandex_api_key}",
                "Content-Type": "application/json"
            }

            # Получаем системный промпт из базы данных
            system_prompt = ai_manager.get_system_prompt()

            data = {
                "modelUri": f"gpt://{self.yandex_folder_id}/yandexgpt-lite",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.1,
                    "maxTokens": max_tokens
                },
                "messages": [
                    {
                        "role": "system",
                        "text": system_prompt
                    },
                    {
                        "role": "user",
                        "text": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data, timeout=10)

            if response.status_code == 200:
                result = response.json()
                return result['result']['alternatives'][0]['message']['text']
            else:
                logger.error(f"YandexGPT API error: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error querying YandexGPT: {e}")
            return None

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        welcome_text = ai_manager.get_greeting_message()
        await update.message.reply_text(welcome_text)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = f"""🏠 Помощь бота {self.bot_name}

📋 Что я могу сделать:
• Проверить адрес в зоне обслуживания УК "Аспект"
• Подсказать варианты улиц
• Помочь с информацией об услугах

💡 Как использовать:
1. Просто напишите адрес в свободной форме
   - "Улица Ленина, дом 25"
   - "Ленина 25"
   - "Мацестинская, 15"

2. Напишите "покажи улицы" - чтобы увидеть улицы в зоне обслуживания

3. Используйте /start - для начала диалога

⚠️ Правила общения:
• Будьте вежливы
• Избегайте нецензурной лексики

Для связи с УК "Аспект" воспользуйтесь контактами в инструкции."""

        await update.message.reply_text(help_text)

    async def show_streets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать улицы в зоне обслуживания"""
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        streets = await self.get_available_streets()
        if streets:
            response = f"""📍 Улицы в зоне обслуживания УК "Аспект":

{chr(10).join([f"• {street}" for street in streets[:20]])}

{'...' if len(streets) > 20 else f''}

💡 Просто напишите название улицы и номер дома для проверки."""
        else:
            response = """❌ К сожалению, не удалось загрузить список улиц.

Пожалуйста, попробуйте позже или напишите адрес напрямую для проверки."""

        await update.message.reply_text(response)

    async def get_available_streets(self):
        """Получение списка улиц из базы данных"""
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT name
                    FROM kladr_address_objects
                    WHERE level = '2' -- улицы
                    ORDER BY name
                    LIMIT 20;
                """)

                streets = [row[0] for row in cursor.fetchall()]
                return streets

        except Exception as e:
            logger.error(f"Ошибка при получении улиц: {e}")
            return []

    async def check_address_in_database(self, address_text):
        """Проверка адреса в базе КЛАДР"""
        try:
            from django.db import connection

            async def check_db():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT kao.name, b.house_number, b.porch_count, b.floor_count
                        FROM kladr_address_objects kao
                        LEFT JOIN buildings b ON kao.id = b.address_object_id
                        WHERE LOWER(kao.name) LIKE LOWER(%s) OR
                              LOWER(b.house_number) LIKE LOWER(%s) OR
                              (LOWER(kao.name || ' ' || COALESCE(b.house_number, '')) LIKE LOWER(%s))
                        LIMIT 10;
                    """, [f'%{address_text}%', f'%{address_text}%', f'%{address_text}%'])

                    results = cursor.fetchall()

                    if results:
                        return True, results
                    else:
                        return False, None

            return await check_db()

        except Exception as e:
            logger.error(f"Ошибка при проверке адреса: {e}")
            return False, None

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик сообщений с использованием AI промптов"""
        user_id = update.effective_user.id
        message_text = update.message.text.strip().lower()
        user_state = self.get_conversation_state(user_id)
        original_text = update.message.text.strip()

        # Показываем, что бот печатает
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        # === ПРОВЕРКА НА ПРИВЕТСТВИЯ ===
        greetings = ['привет', 'здравствуй', 'здравствуйте', 'добрый день', 'доброе утро', 'добрый вечер', 'тук-тук', 'ку-ку']
        if any(greet in message_text for greet in greetings):
            response = ai_manager.get_greeting_message()
            await update.message.reply_text(response)
            return

        # === КОМАНДА ПОКАЗА УЛИЦ ===
        streets_commands = ['покажи улицы', 'улицы', 'список улиц', 'какие улицы']
        if any(cmd in message_text for cmd in streets_commands):
            await self.show_streets(update, context)
            return

        # === ПРОВЕРКА НА ВОПРОСЫ О БОТЕ ===
        bot_questions = ['ты бот', 'ты кто', 'что такое', 'почему не', 'почему сразу']
        if any(question in message_text for question in bot_questions):
            response = ai_manager.get_default_response()
            await update.message.reply_text(response)
            return

        # === ПРОВЕРКА НА ВОПРОСЫ ОБ УСЛУГАХ И ОБЩИЕ ВОПРОСЫ ===
        service_questions = [
            'услуги', 'что вы делаете', 'чем занимаетесь', 'расскажи про услуги',
            'какие услуги', 'что можете', 'помощь', 'что предлагаешь',
            'расскажи о себе', 'о компании', 'деятельность', 'работа'
        ]
        if any(question in message_text for question in service_questions):
            response = f"""Я Сигизмунд Лазоревич, помощник управляющей компании "Аспект".

🏠 **Основные услуги нашей компании:**
- Текущий ремонт и обслуживание многоквартирных домов
- Сантехнические работы и обслуживание систем водоснабжения
- Электромонтажные работы и обслуживание электросетей
- Ремонт и обслуживание систем отопления
- Благоустройство придомовых территорий
- Уборка мест общего пользования
- Подготовка домов к сезонной эксплуатации

📍 **Чтобы проверить адрес:** Просто отправьте адрес в свободной форме, и я проверю, находится ли он в нашей зоне обслуживания.

💡 **Например:** "ул. Ленина, д. 25" или просто "Ленина 25"

Для получения более подробной информации обращайтесь в нашу компанию!"""
            await update.message.reply_text(response)
            return

        # === ПРОВЕРКА НА РУГАТЕЛЬСТВА ===
        if self.contains_profanity(message_text):
            user_state.warnings_count += 1

            if user_state.warnings_count == 1:
                response = ai_manager.get_profanity_warning()
                await update.message.reply_text(response)
                return
            elif user_state.warnings_count >= 2:
                response = ai_manager.get_farewell_message()
                del self.conversations[user_id]
                await update.message.reply_text(response)
                return

        # === ПРОВЕРКА НА КОРОТКИЕ СООБЩЕНИЯ ===
        if len(message_text) < 3:
            response = ai_manager.get_default_response()
            await update.message.reply_text(response)
            return

        # === ПРОВЕРКА ЯВЛЯЕТСЯ ЛИ СООБЩЕНИЕ АДРЕСОМ ===
        # Проверяем, есть ли в сообщении признаки адреса
        address_indicators = [
            'ул.', 'улица', 'пер.', 'переулок', 'просп.', 'проспект', 'пр.',
            'д.', 'дом', 'корп.', 'корпус', 'кв.', 'квартира', 'подъезд',
            'строй', 'строение', 'участок'
        ]

        # Если есть цифры, вероятно это адрес
        has_numbers = bool(re.search(r'\d+', message_text))

        # Проверяем на признаки адреса или содержательные вопросы
        if not (has_numbers or any(ind in message_text for ind in address_indicators)):
            # Если это не похоже на адрес, даем подсказку
            response = f"""Я помогу проверить адрес в зоне обслуживания УК "Аспект".

📍 **Для проверки адреса:** отправьте адрес в любой форме:
- ул. Ленина, д. 25
- Ленина 25, кв. 12
- Мацестинская улица, 15/3
- Проспект Черноморский, дом 7

💡 **Для списка улиц:** напишите "покажи улицы"

📋 **Наши услуги:** напишите "расскажи про услуги"

🤖 **О себе:** напишите "кто ты" """
            await update.message.reply_text(response)
            return

        # === ОСНОВНАЯ ЛОГИКА ПРОВЕРКИ АДРЕСА ===
        # Проверка в базе данных
        is_found, db_results = await self.check_address_in_database(original_text)

        if is_found and db_results:
            # АДРЕС НАЙДЕН - используем AI промпт
            building_info = ""
            if db_results[0][2]:  # porch_count
                building_info += f"\n🏢 Подъездов: {db_results[0][2]}"
            if db_results[0][3]:  # floor_count
                building_info += f"\n🏗️ Этажей: {db_results[0][3]}"

            response = ai_manager.format_address_response(
                address=original_text,
                found=True,
                building_info=building_info,
                additional_info="\n\n🔧 Мы выполняем все виды работ по обслуживанию дома"
            )

            # Сбрасываем счетчик попыток при успехе
            user_state.address_attempts = 0

        else:
            # АДРЕС НЕ НАЙДЕН
            if user_state.address_attempts == 1 and any(word in message_text for word in ['улица', 'ул ', 'проспект', 'пр ', 'переулок', 'пер ']):
                # Возможно, нужно уточнить номер дома
                user_state.address_attempts += 1
                response = f"""Вижу, вы указали улицу. Пожалуйста, уточните номер дома.

Например: "{original_text}, дом 5" или просто добавьте номер дома.

Для показа всех улиц нашей зоны обслуживания напишите "покажи улицы" """
            else:
                # Полностью не найден - используем AI промпт
                response = ai_manager.get_address_not_found_message(original_text)

        await update.message.reply_text(response)

        # Сбрасываем предупреждения если общение вежливое
        if user_state.warnings_count > 0 and not self.contains_profanity(message_text):
            user_state.warnings_count = max(0, user_state.warnings_count - 1)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок с использованием AI промптов"""
        logger.error(f"Update {update} caused error {context.error}")

        if update and update.message:
            response = ai_manager.get_error_message()
            await update.message.reply_text(response)

def main():
    """Основная функция бота"""
    # Установка переменных окружения для Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

    # Инициализация Django
    import django
    django.setup()

    # Перезагружаем промпты при запуске
    ai_manager.reload_prompts()

    # Создание бота
    bot = AddressCheckerBot()

    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("streets", bot.show_streets))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Добавление обработчика ошибок
    application.add_error_handler(bot.error_handler)

    print(f"Бот {bot.bot_name} запускается с AI промптами из базы данных...")

    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()