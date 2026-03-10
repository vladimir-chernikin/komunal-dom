import os
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import google.generativeai as genai
from django.db import connection
from decouple import config

# Настройки логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_TOKEN = config('TELEGRAM_TOKEN', default='7668798774:AAGC8IZoBtS_x5xaAKXa8wlZPcnSPxhPoEc')
GEMINI_API_KEY = config('GEMINI_API_KEY', default='AIzaSyAXk2RkTJ6mh_EeGgNjU0kCrXvd_rKGaDY')
YANDEX_API_KEY = config('YANDEX_API_KEY')
YANDEX_FOLDER_ID = config('YANDEX_FOLDER_ID')

# Инициализация Gemini
genai.configure(api_key=GEMINI_API_KEY)

class AddressCheckerBot:
    def __init__(self):
        self.bot_name = "Сигизмунд Лазоревич"
        self.model = genai.GenerativeModel('gemini-1.5-flash-lite')

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start"""
        welcome_text = f"""🏢 Доброго дня! Меня зовут {self.bot_name}.

Я специализируюсь на проверке адресов в зоне обслуживания УК "Аспект".

🔍 Просто отправьте мне адрес в свободной форме, и я проверю:
- Находится ли адрес в зоне нашей работы
- Проводим ли мы там работы

📝 Примеры:
• ул. Ленина, дом 25, кв. 12
• г. Москва, улица Тверская, 1
• Ленинский район, ул. Советская, д. 15, кв. 7

⚡ Проверьте ваш адрес прямо сейчас!"""

        await update.message.reply_text(welcome_text)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help"""
        help_text = f"""🤖 Справка по боту {self.bot_name}

🔍 Что я делаю:
Проверяю адреса в зоне обслуживания УК "Аспект"

📝 Как проверить адрес:
1. Напишите адрес в свободной форме
2. Можно указать: улицу, дом, квартиру, город, район
3. Я отвечу: в зоне обслуживания или нет

📋 Примеры адресов:
• ул. Ленина, дом 25, кв. 12
• г. Москва, улица Тверская, 1
• Московская область, г. Орехово-Зуево, ул. Советская, д. 15, кв. 7

💡 Советы:
• Можно писать сокращения: ул., д., кв.
• Опечатки не страшны - я постараюсь понять
• Чем точнее адрес, тем точнее результат

🆘 Проблемы?
Если бот не отвечает, проверьте правильность написания адреса.

🏢 УК "Аспект" - Ваш управляющий компаньон"""

        await update.message.reply_text(help_text)

    async def check_address_in_database(self, address_text):
        """Проверка адреса через базу данных КЛАДР"""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def check_db():
            try:
                from django.db import connections
                cursor = connections['default'].cursor()

                # Ищем по КЛАДР таблицам: улицы + здания
                cursor.execute("""
                    SELECT DISTINCT
                        kao.name as street_name,
                        kt.type_full as street_type,
                        b.house_number,
                        kao.kladr_code
                    FROM kladr_address_objects kao
                    LEFT JOIN buildings b ON b.parent_ao_id = kao.ao_id
                    LEFT JOIN kladr_types kt ON kt.type_id = kao.type_id
                    WHERE
                        LOWER(kao.name) LIKE LOWER(%s) OR
                        LOWER(b.house_number) LIKE LOWER(%s) OR
                        (LOWER(kao.name || ' ' || COALESCE(b.house_number, '')) LIKE LOWER(%s))
                    LIMIT 10;
                """, [f'%{address_text}%', f'%{address_text}%', f'%{address_text}%'])

                results = cursor.fetchall()

                if results:
                    return True, results
                else:
                    return False, None

            except Exception as e:
                logger.error(f"Ошибка при проверке адреса в БД: {e}")
                return False, None  # При ошибке считаем, что адрес не найден

        return await check_db()

    async def check_address_with_ai(self, address_text):
        """Анализ и дополнение адреса с помощью AI"""
        try:
            # Получаем список улиц из базы (ограничим для скорости)
            streets = await self.get_available_streets()

            # Упрощенный промпт для быстрого ответа
            prompt = f"""
            Адрес: "{address_text}"

            Доступные улицы: {", ".join(streets[:10])}

            Проанализируй и ответь JSON:
            {{
                "street": "найденная улица или null",
                "house": "номер дома или null",
                "confidence": "high/medium/low",
                "suggestions": ["список похожих улиц"],
                "questions": ["что уточнить?"]
            }}
            """

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=200,
                    temperature=0.1
                )
            )
            return response.text

        except Exception as e:
            logger.error(f"Ошибка при анализе адреса AI: {e}")
            return None

    async def get_available_streets(self):
        """Получаем список улиц из базы"""
        from asgiref.sync import sync_to_async

        @sync_to_async
        def get_streets():
            try:
                from django.db import connections
                cursor = connections['default'].cursor()

                cursor.execute("""
                    SELECT DISTINCT
                        kt.type_full || ' ' || kao.name as full_street,
                        kao.name
                    FROM kladr_address_objects kao
                    LEFT JOIN kladr_types kt ON kt.type_id = kao.type_id
                    WHERE kao.kladr_level = 7
                    ORDER BY kao.name
                    LIMIT 50;
                """)

                results = cursor.fetchall()
                return [result[0] for result in results]
            except:
                return []

        return await get_streets()

    def is_address_message(self, text):
        """Проверяет, является ли сообщение адресом"""
        # Ключевые слова, которые могут указывать на адрес
        address_keywords = [
            'ул', 'улица', 'д', 'дом', 'кв', 'квартира', 'г', 'город',
            'р-н', 'район', 'пос', 'поселок', 'деревня', 'мкр', 'микрорайон',
            'проспект', 'пр-т', 'пр', 'переулок', 'пер', 'шоссе', 'ш',
            'корпус', 'корп', 'строение', 'стр'
        ]

        text_lower = text.lower()

        # Если есть ключевые слова адреса
        for keyword in address_keywords:
            if keyword in text_lower:
                return True

        # Если есть цифры (номер дома/квартиры)
        if any(char.isdigit() for char in text):
            return True

        # Если это короткое сообщение (возможно стук/приветствие)
        if len(text.strip()) < 10:
            return False

        # Если содержит слова-приветствия
        greetings = ['привет', 'здравствуй', 'добрый', 'тук', 'hello', 'hi']
        for greeting in greetings:
            if greeting in text_lower:
                return False

        return True

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        address_text = update.message.text.strip()

        # Проверяем, является ли сообщение адресом
        if not self.is_address_message(address_text):
            # Если не адрес, отвечаем по умолчанию
            await update.message.reply_text(
                "👋 Здравствуйте! Я помогаю проверить адреса в зоне обслуживания УК \"Аспект\".\n\n"
                "🔍 Отправьте мне адрес для проверки (например: ул. Ленина, дом 25).\n"
                "❓ Или напишите /help для подробной справки."
            )
            return

        # Показываем, что бот печатает
        await update.message.chat.send_action(action="typing")

        # Изначальный ответ
        await update.message.reply_text(f"🔍 Анализирую адрес: \"{address_text}\"...")

        # Сначала пытаемся найти точное совпадение в базе
        is_found, db_results = await self.check_address_in_database(address_text)

        if is_found:
            # Адрес найден - показываем результат
            response_text = f"""✅ Адрес в зоне обслуживания УК "Аспект"!

📍 {address_text}

🏢 Отличные новости! По этому адресу мы проводим все виды работ:
• Ремонт и обслуживание коммуникаций
• Сантехнические работы
• Электромонтажные работы
• Общие работы по содержанию дома"""

            # Добавляем детали из БД если найдены
            if db_results:
                response_text += f"\n\n🔍 Найдено в базе КЛАДР: {len(db_results)} вариантов"
                for result in db_results[:3]:
                    street_name, street_type, house_number, kladr_code = result
                    if house_number:
                        response_text += f"\n• {street_type} {street_name}, д. {house_number}"
                    else:
                        response_text += f"\n• {street_type} {street_name}"

            response_text += "\n\n📞 Для заявки на услуги:\n📧 admin@komunal-dom.ru\n🌐 www.komunal-dom.ru"

            await update.message.reply_text(response_text)
            return

        # AI временно отключен из-за проблем с API
        # Используем простую логику с наводящими вопросами

        # Простая логика анализа адреса без AI
        response = f"🔍 **Результат анализа адреса:**\n\n"
        response += "❓ **Не удалось однозначно определить адрес.**\n\n"

        # Пытаемся извлечь информацию из адреса
        import re

        # Ищем номер дома
        house_match = re.search(r'(?:д\.?|дом|№?\s*)?(\d+[а-яА-Я]?)', address_text)
        house_number = house_match.group(1) if house_match else None

        # Ищем название улицы
        street_keywords = ['ул', 'улица', 'пр', 'проспект', 'пер', 'переулок', 'ш', 'шоссе']
        street_text = address_text
        for keyword in street_keywords:
            street_text = street_text.replace(keyword, '')
        street_text = street_text.strip()

        # Убираем номер дома из названия улицы
        if house_number:
            street_text = re.sub(r'(?:д\.?|дом|№?\s*)?' + house_number, '', street_text).strip()

        if street_text:
            response += f"🏠 Вероятная улица: {street_text}\n"
        if house_number:
            response += f"🏡 Номер дома: {house_number}\n"

        # Предлагаем похожие варианты
        suggested_addr = street_text + ', ' + house_number if street_text and house_number else address_text
        response += "\n💡 Попробуйте:\n• " + suggested_addr + "\n• Уточнить номер дома (если не указан)\n• Проверить название улицы\n\nДоступные улицы в зоне:\n• Мацестинская\n• Гагарина\n• Красноармейская\n• Ленина\n• И другие..."

        response += f"\n\n💭 **Ваш запрос:** {address_text}"
        response += "\n\n📝 Введите полный адрес (улица, номер дома) для точной проверки."

        await update.message.reply_text(response, parse_mode='Markdown')

        if ai_response:
            try:
                # Пытаемся распарсить JSON ответ
                import json
                ai_data = json.loads(ai_response)

                response = f"🔍 **Результат анализа адреса:**\n\n"

                if ai_data.get('confidence') == 'high' and ai_data.get('full_address'):
                    # Высокая уверенность - проверяем полный адрес
                    full_addr = ai_data['full_address']
                    is_found, db_results = await self.check_address_in_database(full_addr)

                    if is_found:
                        response += f"✅ **Найден адрес:** {full_addr}\n\n"
                        response += f"📍 Адрес в зоне обслуживания УК \"Аспект\"!\n\n"
                        response += "🏢 Предлагаем следующие услуги:\n"
                        response += "• Ремонт и обслуживание коммуникаций\n"
                        response += "• Сантехнические работы\n"
                        response += "• Электромонтажные работы\n\n"
                        response += "📞 Для заявки:\n📧 admin@komunal-dom.ru\n🌐 www.komunal-dom.ru"
                    else:
                        response += f"❌ Уточненный адрес **{full_addr}** не найден в зоне обслуживания.\n\n"
                        response += "🔧 Можем выполнить работы на платной основе.\n\n"
                        response += "📞 Для расчета стоимости:\n📧 admin@komunal-dom.ru"
                else:
                    # Низкая уверенность - задаем наводящие вопросы
                    response += "❓ **Не удалось однозначно определить адрес.**\n\n"

                    if ai_data.get('street'):
                        response += f"🏠 Улица: {ai_data['street']}\n"

                    if ai_data.get('suggestions'):
                        response += f"\n💡 **Возможно, вы имели в виду:**\n"
                        for suggestion in ai_data['suggestions'][:3]:
                            response += f"• {suggestion}\n"

                    if ai_data.get('questions'):
                        response += f"\n🔍 **Пожалуйста, уточните:**\n"
                        for question in ai_data['questions'][:3]:
                            response += f"• {question}\n"

                    response += f"\n\n💭 **Ваш запрос:** {address_text}"
                    response += "\n\n📝 Попробуйте ввести адрес более подробно или выберите из предложенных вариантов."

                await update.message.reply_text(response, parse_mode='Markdown')

            except (json.JSONDecodeError, KeyError):
                # Если не удалось распарсить JSON
                response = f"🤖 **Анализ завершен:**\n\n{ai_response[:500]}\n\n"
                response += "❌ Адрес не найден в зоне обслуживания.\n\n"
                response += "🔧 Можем выполнить работы на платной основе.\n\n"
                response += "📞 Свяжитесь с нами:\n📧 admin@komunal-dom.ru"

                await update.message.reply_text(response, parse_mode='Markdown')
        else:
            # AI не ответил - стандартный ответ
            response_text = f"""❌ Адрес вне зоны обслуживания

📍 {address_text}

⚠️ УК "Аспект" не обслуживает этот адрес.

🔧 Можем выполнить работу на платной основе:
• Качественные материалы
• Квалифицированные специалисты
• Гарантия на выполненные работы

📞 Свяжитесь с нами для расчета стоимости:
• 📧 admin@komunal-dom.ru
• 🌐 www.komunal-dom.ru

💡 Проверьте правильность написания адреса или уточните детали."""

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Update {update} caused error {context.error}")

        if update and update.message:
            await update.message.reply_text(
                "⚠️ Произошла ошибка. Попробуйте еще раз или обратитесь в поддержку."
            )

def main():
    """Основная функция бота"""
    # Устанавливаем переменные окружения для Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

    # Инициализация Django
    import django
    django.setup()

    # Создаем экземпляр бота
    bot = AddressCheckerBot()

    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Добавляем обработчик ошибок
    application.add_error_handler(bot.error_handler)

    print(f"🤖 Бот {bot.bot_name} запускается...")

    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()