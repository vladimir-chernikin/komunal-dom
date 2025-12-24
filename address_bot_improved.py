#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram бот для проверки адресов в зоне обслуживания УК "Аспект"
Улучшенная версия с профессиональной речью и фильтрацией контента
"""

import asyncio
import logging
import os
import re
import sys
import html
from decouple import config

# Telegram imports
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Django setup
sys.path.append('/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

# Настройки
TELEGRAM_TOKEN = config('TELEGRAM_TOKEN')
GEMINI_API_KEY = config('GEMINI_API_KEY', default='AIzaSyAXk2RkTJ6mh_EeGgNjU0kCrXvd_rKGaDY')
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
    """Улучшенный бот для проверки адресов"""

    def __init__(self):
        self.bot_name = "Сигизмунд Лазоревич"
        # Инициализация YandexGPT вместо Gemini
        try:
            import requests
            self.use_yandex = True
            self.yandex_api_key = YANDEX_API_KEY
            self.yandex_folder_id = YANDEX_FOLDER_ID
        except:
            self.use_yandex = False

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
        """Запрос к YandexGPT API"""
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
                        "text": """Вы - профессиональный оператор call-центра УК "Аспект".

ВАЖНЫЕ ПРАВИЛА:
1. Говорите строго по-русски, без эмодзи и смайликов
2. Будьте вежливы и профессиональны
3. При ругательствах - вежливо напомните о профессиональном общении
4. Не давайте информацию, не касающуюся обслуживания УК
5. Если адрес неполный - вежливо попросите уточнить
6. Запоминайте контекст разговора

Отвечайте как человек, работающий в call-центре."""
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
        welcome_text = f"""Доброго дня! Меня зовут {self.bot_name}.

Я специалист по проверке адресов в зоне обслуживания УК "Аспект".

Просто напишите адрес, и я проверю, обслуживаем ли мы этот адрес.

Если нужна помощь - напишите команду /help"""

        await update.message.reply_text(welcome_text)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = """Как я могу помочь:

1. Проверка адреса:
   Просто напишите адрес в любом формате
   Пример: "улица Ленина дом 25" или "Ленина 25"

2. Если адрес неполный:
   Я вежливо попрошу вас уточнить информацию

3. Обслуживание:
   Я сообщу, обслуживается ли адрес УК "Аспект"
   Если нет - предложу платные варианты

4. Правила общения:
   Пожалуйста, будьте вежливы
   Избегайте нецензурной лексики

Для связи с УК "Аспект":
   Телефон: по основному номеру организации
   Email: admin@komunal-dom.ru
   Сайт: www.komunal-dom.ru"""

        await update.message.reply_text(help_text)

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
                        SELECT kao.name, b.house_number
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

    async def analyze_address_with_ai(self, address_text, user_state):
        """Анализ адреса с учетом контекста и профессиональной речью"""

        # Получаем доступные улицы
        streets = await self.get_available_streets()

        # Создаем промпт с учетом контекста
        context_info = ""
        if user_state.last_address:
            context_info = f"\nПредыдущий запрос: {user_state.last_address}"
        if user_state.address_attempts > 1:
            context_info += f"\nКоличество попыток: {user_state.address_attempts}"

        prompt = f"""Клиент указал адрес: "{address_text}"
{context_info}

Доступные улицы в зоне обслуживания: {", ".join(streets[:15])}

Проанализируйте адрес как профессиональный оператор:

1. Если адрес полный и точный - подтвердите
2. Если адрес неполный - вежливо попросите уточнить
3. Если есть похожие варианты - предложите их
4. Учитывайте предыдущие попытки клиента

Отвечайте профессионально, без эмодзи, как в call-центре.

Формат ответа:
АНАЛИЗ: [краткий анализ]
ДЕЙСТВИЕ: [FOUND/CLARIFY/SUGGEST/NOT_FOUND]
СООБЩЕНИЕ: [текст ответа клиенту]
ВАРИАНТЫ: [список вариантов если нужно]
"""

        ai_response = await self.ask_yandexgpt(prompt)

        if not ai_response:
            # Запасной вариант без ИИ
            return self.fallback_address_analysis(address_text, streets)

        return ai_response

    def fallback_address_analysis(self, address_text, streets):
        """Запасной анализ без ИИ"""
        text_lower = address_text.lower()

        # Ищем совпадения с улицами
        found_streets = []
        for street in streets:
            if street.lower() in text_lower:
                found_streets.append(street)

        if found_streets:
            return f"""АНАЛИЗ: Найдена улица {found_streets[0]}
ДЕЙСТВИЕ: CLARIFY
СООБЩЕНИЕ: Вижу, вы указали улицу {found_streets[0]}. Пожалуйста, уточните номер дома.
ВАРИАНТЫ: {found_streets[0]}, номер дома?"""
        else:
            return f"""АНАЛИЗ: Адрес не найден в зоне обслуживания
ДЕЙСТВИЕ: NOT_FOUND
СООБЩЕНИЕ: К сожалению, указанный адрес не находится в зоне обслуживания УК "Аспект". Мы можем выполнить работы на платной основе. Пожалуйста, свяжитесь с нами для расчета стоимости.
ВАРИАНТЫ: []"""

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик сообщений"""
        user_id = update.effective_user.id
        message_text = update.message.text.strip()
        user_state = self.get_conversation_state(user_id)

        # Проверка на ругательства
        if self.contains_profanity(message_text):
            user_state.warnings_count += 1

            if user_state.warnings_count == 1:
                response = """Прошу вас общаться в вежливой форме. Я здесь, чтобы помочь вам с проверкой адреса.

Пожалуйста, изложите ваш вопрос корректно, и я с удовольствием помогу."""

                await update.message.reply_text(response)
                return

            elif user_state.warnings_count >= 2:
                response = """Приношу извинения, но вынужден прервать разговор при использовании нецензурной лексики.

Если у вас возникнут вопросы по адресу или обслуживанию, пожалуйста, свяжитесь с УК "Аспект" напрямую:
Телефон: по основному номеру
Email: admin@komunal-dom.ru
Сайт: www.komunal-dom.ru

Желаю вам хорошего дня."""

                # Сбрасываем состояние диалога
                del self.conversations[user_id]
                await update.message.reply_text(response)
                return

        # Проверка на системные сообщения
        if len(message_text) < 3:
            return

        # Показываем, что бот печатает
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        # Обновляем состояние
        user_state.last_address = message_text
        user_state.address_attempts += 1
        user_state.last_question_time = update.message.date

        # Анализ адреса
        ai_response = await self.analyze_address_with_ai(message_text, user_state)

        # Дополнительная проверка в базе данных
        is_found, db_results = await self.check_address_in_database(message_text)

        # Формируем ответ
        if is_found and db_results:
            response = f"""Да, этот адрес находится в зоне обслуживания УК "Аспект".

Найденные варианты:
{chr(10).join([f"- {row[0]} {row[1] or ''}" for row in db_results[:3]])}

Мы выполняем все виды работ по обслуживанию дома и коммуникаций:
- Ремонт и обслуживание инженерных систем
- Сантехнические работы
- Электромонтажные работы
- Общие работы по содержанию дома

Для заявки на обслуживание, пожалуйста, свяжитесь с нами:
Email: admin@komunal-dom.ru
Сайт: www.komunal-dom.ru"""

        elif "АНАЛИЗ:" in ai_response:
            # Используем ответ ИИ
            response = ai_response.replace("АНАЛИЗ:", "").replace("ДЕЙСТВИЕ:", "").replace("СООБЩЕНИЕ:", "").replace("ВАРИАНТЫ:", "")
            response = response.strip()

        else:
            # Стандартный ответ если не найдено
            response = f"""К сожалению, адрес "{message_text}" не найден в зоне обслуживания УК "Аспект".

Мы можем выполнить работы на платной основе. Для расчета стоимости, пожалуйста:

- Свяжитесь по Email: admin@komunal-dom.ru
- Посетите сайт: www.komunal-dom.ru

Если вы считаете, что адрес должен быть в нашей зоне обслуживания, пожалуйста, проверьте правильность написания или уточните детали."""

        await update.message.reply_text(response)

        # Сбрасываем счетчик предупреждений если общение было продуктивным
        if user_state.warnings_count > 0 and not self.contains_profanity(message_text):
            user_state.warnings_count = max(0, user_state.warnings_count - 1)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Update {update} caused error {context.error}")

        if update and update.message:
            await update.message.reply_text(
                "Извините, произошла техническая ошибка. Пожалуйста, попробуйте еще раз или свяжитесь с поддержкой."
            )

def main():
    """Основная функция бота"""
    # Установка переменных окружения для Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

    # Инициализация Django
    import django
    django.setup()

    # Создание бота
    bot = AddressCheckerBot()

    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Добавление обработчика ошибок
    application.add_error_handler(bot.error_handler)

    print(f"Бот {bot.bot_name} запускается в улучшенной версии...")

    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()