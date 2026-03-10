#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Telegram бот для проверки адресов и обработки заявок УК "Аспект"
РЕФАКТОРЕННАЯ ВЕРСИЯ - использует новую систему AI
"""

import asyncio
import logging
import os
import sys
import uuid
from decouple import config

# Telegram imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

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


class RefactoredAddressBot:
    """Рефакторенный бот с новой архитектурой"""

    def __init__(self):
        self.bot_name = "Сигизмунд Лазоревич"

        # Инициализируем новые компоненты
        self.orchestrator = ServiceDetectionOrchestrator()

        # Хранилище диалогов
        self.dialogs = {}

        logger.info(f"Бот {self.bot_name} инициализирован с новой системой AI")

    def get_or_create_dialog(self, user_id: int, telegram_user_id: int) -> DialogMemoryManager:
        """Получить или создать диалог"""
        if user_id not in self.dialogs:
            # Создаем новый диалог с UUID
            dialog_id = str(uuid.uuid4())
            self.dialogs[user_id] = DialogMemoryManager(dialog_id, telegram_user_id)
            logger.info(f"Создан новый диалог для пользователя {user_id}")

        return self.dialogs[user_id]

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name or update.effective_user.username

        # Получаем или создаем диалог
        dialog = self.get_or_create_dialog(user_id, user_id)

        # Сохраняем имя пользователя
        if user_name:
            dialog.extract_user_name(f"Меня зовут {user_name}")
            dialog.save_to_database()

        welcome_message = f"""
👋 Здравствуйте, {user_name}!

Я {self.bot_name}, ваш умный помощник от управляющей компании "Аспект".

✨ **Я теперь умею:**
- 🔍 Распознавать тип проблемы (течь крана, отсутствие воды и т.д.)
- 🧠 Запоминать ваше имя и собирать адрес по частям
- 🚫 Отсекать спам и нецензурную лексику
- 📋 Создавать красивые заявки для подтверждения
- 💰 Контролировать расходы на AI

**Как пользоваться:**
1️⃣ Просто опишите вашу проблему
2️⃣ Я помогу собрать полный адрес по частям
3️⃣ Вы подтвердите созданную заявку

Например: "Течет кран на кухне на ул. Ленина 15"

Попробуйте! 🚀
        """

        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = f"""
🤖 **Помощь по боту {self.bot_name}**

**Команды:**
/start - Приветствие и создание диалога
/help - Эта справка
/cancel - Отмена текущего диалога

**Как использовать:**
📝 Опишите вашу проблему обычным языком
📍 Я помогу определить точный адрес
✅ Вы подтвердите созданную заявку

**Примеры сообщений:**
- "Протекает кран на кухне"
- "Нет воды по адресу Советская 15"
- "Шумит труба в подъезде"
- "Проверьте ул. Ленина дом 25 кв 12"

**Я умею распознавать:**
- Утечки воды, протечки
- Отсутствие воды/тепла
- Шум, вибрации
- Засоры, засорение
- И многие другие проблемы!

🚀 Попробуйте сейчас!
        """

        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /cancel"""
        user_id = update.effective_user.id

        if user_id in self.dialogs:
            dialog = self.dialogs[user_id]
            dialog.clear_context()
            dialog.save_to_database()

            await update.message.reply_text(
                "🔄 Диалог сброшен. Все данные очищены.\n"
                "Новая проблема? Опишите её! 📝"
            )
        else:
            await update.message.reply_text(
                "❌ У вас нет активного диалога.\n"
                "Начните с описания проблемы! 📝"
            )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик сообщений"""
        try:
            user_id = update.effective_user.id
            message_text = update.message.text.strip()

            if not message_text:
                return

            # Получаем или создаем диалог
            dialog = self.get_or_create_dialog(user_id, user_id)

            logger.info(f"Сообщение от {user_id}: {message_text}")

            # Обрабатываем через orchestrator
            result = self.orchestrator.process_message(
                message_text=message_text,
                telegram_user_id=user_id,
                telegram_username=update.effective_user.username,
                dialog_id=dialog.dialog_id
            )

            # Обрабатываем результат
            if result['status'] == 'SUCCESS':
                await self._handle_success_result(update, result, dialog)
            elif result['status'] == 'NEED_ADDRESS':
                await self._handle_need_address(update, result, dialog)
            elif result['status'] == 'SPAM':
                await self._handle_spam_result(update, result, dialog)
            elif result['status'] == 'REJECT':
                await self._handle_reject_result(update, result, dialog)
            else:
                await self._handle_unclear_result(update, result, dialog)

        except Exception as e:
            logger.error(f"Ошибка в handle_message: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка. Попробуйте еще раз."
            )

    async def _handle_success_result(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """Обработка успешного результата"""
        try:
            # Создаем финальный JSON
            output_json = self.orchestrator.create_output_json(
                service_id=result['service_id'],
                service_name=result['service_name'],
                service_confidence=result.get('confidence', 0.8),
                address_components=result['address_components'],
                user_name=dialog.user_name,
                user_phone=None,  # Можно добавить позже
                description=result['user_message'],
                trace_id=result.get('trace_id')
            )

            # Сохраняем заявку в БД
            ticket_id = self.orchestrator.save_final_ticket(output_json, dialog.dialog_id)

            # Форматируем для отображения
            formatted_message = self.orchestrator.format_json_for_display(output_json)

            # Создаем кнопки подтверждения
            buttons = self.orchestrator.generate_confirmation_buttons(output_json)
            reply_markup = InlineKeyboardMarkup(buttons) if buttons else None

            await update.message.reply_text(
                formatted_message,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )

            # Сохраняем JSON в context для callback
            if 'context' not in update._bot_data:
                update._bot_data['context'] = {}
            update._bot_data['context'][ticket_id] = output_json

            logger.info(f"Отправлена заявка для подтверждения: {ticket_id}")

        except Exception as e:
            logger.error(f"Ошибка в _handle_success_result: {e}")
            await update.message.reply_text("❌ Ошибка при создании заявки")

    async def _handle_need_address(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """Обработка необходимости уточнения адреса"""
        try:
            # Сохраняем информацию об услуге
            if 'service_id' in result:
                dialog.update_context('current_service', {
                    'service_id': result['service_id'],
                    'service_name': result['service_name'],
                    'confidence': result.get('confidence', 0.8),
                    'detected_at': result.get('trace_id')
                })

            # Накапливаем адресные компоненты
            if 'address_components' in result:
                dialog.accumulate_address_fragments(result['address_components'])

            # Определяем, что еще нужно запросить
            current_address = dialog.get_full_address_string()
            missing_info = self._get_missing_address_info(dialog)

            response_text = f"""
🔍 **Понял проблему**: {result.get('service_name', 'проблема')}

📍 **Адрес**: {current_address if current_address else 'Еще не определен'}

{missing_info}

💡 *Отправьте недостающую информацию и я продолжу helping!*
            """

            await update.message.reply_text(response_text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ошибка в _handle_need_address: {e}")

    def _get_missing_address_info(self, dialog: DialogMemoryManager) -> str:
        """Определить, какой информации об адресе не хватает"""
        missing = []

        if not dialog.extracted_entities.get('street'):
            missing.append("🏠 **Улицу**")

        if not dialog.extracted_entities.get('house_number'):
            missing.append("🏢 **Номер дома**")

        if not dialog.extracted_entities.get('apartment_number'):
            missing.append("🚪 **Номер квартиры** (если есть)")

        if missing:
            return f"**Нужно уточнить**: {', '.join(missing)}"

        return "✅ Адрес определен! Можно создавать заявку."

    async def _handle_spam_result(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """Обработка спама"""
        category = result.get('category', 'SPAM')

        if category == 'PROFANITY':
            response = "🚫 **Сообщение содержит нецензурную лексику**\n\nПожалуйста, ведите себя уважительно."
        elif category == 'NON_CONSTRUCTIVE':
            response = "😐 **Не удалось определить конструктивное содержание**\n\nПопробуйте более четко описать вашу проблему."
        elif category == 'VAGUE':
            response = "❓ **Сообщение слишком расплывчатое**\n\nПожалуйста, опишите проблему подробнее."
        else:
            response = "🚫 **Сообщение определено как спам**\n\nПопробуйте еще раз с другим текстом."

        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_reject_result(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """Обработка отклонения"""
        response = f"""
❌ **Не удалось обработать сообщение**

**Причина:** {result.get('reason', 'неизвестна')}

💡 **Попробуйте:**
- Описать проблему более четко
- Указать полный адрес
- Избегать сложных формулировок

**Пример:** "Течет кран на кухне по адресу ул. Ленина, дом 15, квартира 42"
        """

        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_unclear_result(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """Обработка неясного результата"""
        response = f"""
🤔 **Не удалось однозначно определить проблему**

**Текст:** "{result.get('user_message', '')}"

**Попробуйте:**
1️⃣ **Сформулировать проще**: "Течет кран"
2️⃣ **Добавить адрес**: "на ул. Ленина, дом 15"
3️⃣ **Указать место**: "в ванной комнате"

Или напишите **"расскажи про услуги"** для помощи.
        """

        await update.message.reply_text(response, parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        try:
            query = update.callback_query
            await query.answer()

            if query.data == "confirm_yes":
                # Подтверждение заявки
                await query.edit_message_text(
                    "✅ **Заявка подтверждена и отправлена в работу!**\n\n"
                    "Мы свяжемся с вами в ближайшее время.\n"
                    "Благодарим за обращение! 🙏",
                    parse_mode='Markdown'
                )
                logger.info(f"Пользователь {update.effective_user.id} подтвердил заявку")

            elif query.data == "confirm_no":
                # Отмена заявки
                await query.edit_message_text(
                    "❌ **Заявка отменена**\n\n"
                    "Если хотите создать новую - опишите проблему заново! 📝",
                    parse_mode='Markdown'
                )
                logger.info(f"Пользователь {update.effective_user.id} отменил заявку")

        except Exception as e:
            logger.error(f"Ошибка в handle_callback: {e}")


# Инициализация бота
bot_instance = RefactoredAddressBot()


def main():
    """Основная функция запуска бота"""
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", bot_instance.start_command))
    application.add_handler(CommandHandler("help", bot_instance.help_command))
    application.add_handler(CommandHandler("cancel", bot_instance.cancel_command))

    # Обработчик callback для кнопок
    application.add_handler(CallbackQueryHandler(bot_instance.handle_callback))

    # Основной обработчик текстовых сообщений
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance.handle_message)
    )

    logger.info("🚀 Бот Сигизмунд Лазоревич запускается с новой системой AI!")

    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()