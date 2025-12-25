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

# Django async helper
from asgiref.sync import sync_to_async

# Django setup
sys.path.append('/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

# Импортируем необходимые компоненты
from dialog_memory_manager import DialogMemoryManager
from main_agent import MainAgent
from prompt_manager import prompt_manager
from object_detection_service import ObjectDetectionService
from json_formatter_service import JSONFormatterService

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

        # Инициализируем Главного Агента с микросервисной архитектурой
        self.main_agent = MainAgent()

        # Инициализируем новые сервисы
        self.object_detector = ObjectDetectionService()
        self.json_formatter = JSONFormatterService()

        # Хранилище диалогов
        self.dialogs = {}

        logger.info(f"Бот {self.bot_name} инициализирован с MainAgent, ObjectDetector и JSONFormatter")

    async def get_or_create_dialog(self, user_id: int, telegram_user_id: int) -> DialogMemoryManager:
        """
        Получить или создать диалог

        ИСПРАВЛЕНО: Пытается загрузить из базы данных, если нет в памяти
        ИСПРАВЛЕНО: Использует настоящий UUID вместо строки
        """
        if user_id not in self.dialogs:
            # Пытаемся загрузить из базы данных
            # Для постоянства используем UUID5 на основе user_id (детерминированный)
            import uuid as uuid_lib
            dialog_id = str(uuid_lib.uuid5(uuid_lib.NAMESPACE_DNS, f"user_{user_id}"))

            # Пытаемся загрузить из базы
            loaded_dialog = await sync_to_async(DialogMemoryManager.load_from_database)(dialog_id, user_id)

            if loaded_dialog:
                self.dialogs[user_id] = loaded_dialog
                logger.info(f"Загружен существующий диалог для пользователя {user_id}, история: {len(loaded_dialog.conversation_history)} сообщений")
            else:
                # Создаем новый диалог
                self.dialogs[user_id] = DialogMemoryManager(dialog_id, telegram_user_id)
                logger.info(f"Создан новый диалог для пользователя {user_id}")

        return self.dialogs[user_id]

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name or update.effective_user.username

        # Получаем или создаем диалог
        dialog = await self.get_or_create_dialog(user_id, user_id)

        # Сохраняем имя пользователя
        if user_name:
            dialog.extract_user_name(f"Меня зовут {user_name}")
            await sync_to_async(dialog.save_to_database)()

        welcome_message = f"""
Здравствуйте, {user_name}!

Я диспетчер управляющей компании "Аспект".

Пожалуйста, опишите вашу проблему, и я помогу вам её решить.
        """

        await update.message.reply_text(welcome_message, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
Я диспетчер управляющей компании "Аспект".

Просто опишите вашу проблему текстом, например:
- Протекает кран на кухне
- Нет горячей воды
- Шумит труба в подъезде
- Пропал свет

Я приму вашу заявку и направлю специалиста.
        """

        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /cancel"""
        user_id = update.effective_user.id

        if user_id in self.dialogs:
            dialog = self.dialogs[user_id]
            # Сбрасываем состояние диалога
            dialog.conversation_history = []
            dialog.extracted_entities = {
                'street': None,
                'house_number': None,
                'apartment_number': None,
                'entrance': None
            }
            dialog.current_service_context = None
            await sync_to_async(dialog.save_to_database)()

            await update.message.reply_text(
                "Диалог сброшен. Все данные очищены.\n"
                "Новая проблема? Опишите её!"
            )
        else:
            await update.message.reply_text(
                "У вас нет активного диалога.\n"
                "Начните с описания проблемы!"
            )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик сообщений"""
        try:
            user_id = update.effective_user.id
            message_text = update.message.text.strip() if update.message and update.message.text else ""

            logger.info(f"Получено сообщение от {user_id}: '{message_text}'")
            logger.info(f"Полное сообщение: {update.message}")

            if not message_text:
                logger.warning(f"Пустое сообщение от {user_id}")
                await update.message.reply_text(
                    "Не удалось прочитать сообщение.\n"
                    "Пожалуйста, отправьте текстовое сообщение."
                )
                return

            # Проверка на некорректные/слишком короткие сообщения
            if len(message_text.strip()) < 2:
                logger.warning(f"Слишком короткое сообщение от {user_id}: '{message_text}'")
                await update.message.reply_text(
                    "Слишком короткое сообщение.\n"
                    "Пожалуйста, опишите вашу проблему подробнее (минимум 2 символа)."
                )
                return

            # Проверка на потенциально проблемные слова
            forbidden_words = ['жопа', 'пиздец', 'блядь', 'хуй', 'пидор', 'сука']
            message_lower_check = message_text.lower()

            if any(word in message_lower_check for word in forbidden_words):
                logger.warning(f"Сообщение с нецензурной лексикой от {user_id}: '{message_text}'")
                await update.message.reply_text(
                    "Пожалуйста, излагайте проблему в корректной форме без нецензурной лексики.\n"
                    "Опишите, что именно случилось и где это произошло."
                )
                return

            # Получаем или создаем диалог
            dialog = await self.get_or_create_dialog(user_id, user_id)

            logger.info(f"Диалог создан/получен: {dialog.dialog_id}")

            # ИСПРАВЛЕНО: Добавляем сообщение пользователя в историю ДО обработки
            dialog.add_message('user', message_text)

            # Проверяем на специальные сообщения для управления
            message_lower = message_text.lower()

            # Проверка на команды выхода и помощи
            escape_commands = ['связь с диспетчером', 'оператор', 'человек', 'помощь', 'help', 'ошибка']
            if any(cmd in message_lower for cmd in escape_commands):
                logger.info(f"Пользователь {user_id} запрашивает связь с диспетчером: '{message_text}'")
                await update.message.reply_text(
                    "*УК Аспект - Диспетчерская служба*\n\n"
                    "*Экстренные телефоны:*\n"
                    "• Диспетчер: +7 (495) 123-45-67\n"
                    "• Аварийная служба: +7 (495) 123-45-68\n\n"
                    "*Время работы:* 24/7\n\n"
                    "Вы также можете описать вашу проблему, и я постараюсь помочь определить нужную услугу.",
                    parse_mode='Markdown'
                )
                return

            # Проверяем на приветствия
            greetings = ['привет', 'здравствуй', 'добрый день', 'добрый вечер', 'доброе утро', 'здравствуйте']

            if any(greeting in message_lower for greeting in greetings):
                logger.info(f"Обнаружено приветствие от {user_id}")

                greeting_text = f"Здравствуйте, {update.effective_user.first_name}! Я диспетчер УК Аспект. Опишите вашу проблему, пожалуйста."

                await update.message.reply_text(greeting_text)
                return

            # Получаем историю сообщений для контекста
            dialog_history = dialog.conversation_history or []  # Берем историю диалога
            logger.info(f"История диалога ({len(dialog_history)} сообщений): {dialog_history}")

            # ИСПРАВЛЕНО: Передаем оригинальное сообщение, НЕ склеиваем с контекстом
            # MainAgent сам использует dialog_history для анализа контекста
            logger.info(f"Вызываем MainAgent.process_service_detection с текстом: '{message_text}'")

            user_context = {
                'telegram_user_id': user_id,
                'telegram_username': update.effective_user.username,
                'dialog_id': dialog.dialog_id,
                'dialog_history': dialog_history,
                'original_message': message_text,
                'is_followup': len(dialog_history) > 0
            }

            result = await self.main_agent.process_service_detection(message_text, user_context)
            logger.info(f"Результат MainAgent: {result}")

            # Обрабатываем результат
            bot_response = None
            if result['status'] == 'SUCCESS':
                bot_response = await self._handle_main_agent_success(update, result, dialog)
            elif result['status'] == 'AMBIGUOUS':
                bot_response = await self._handle_main_agent_ambiguous(update, result, dialog)
            elif result['status'] == 'ERROR':
                bot_response = await self._handle_main_agent_error(update, result, dialog)
            else:
                bot_response = await self._handle_main_agent_unclear(update, result, dialog)

            # ИСПРАВЛЕНО: Добавляем ответ бота в историю и сохраняем в базу
            if bot_response:
                dialog.add_message('bot', bot_response)

            # Сохраняем историю диалога в базу данных
            await sync_to_async(dialog.save_to_database)()
            logger.info(f"История диалога сохранена, всего сообщений: {len(dialog.conversation_history)}")

        except Exception as e:
            # Детальное логирование ошибки с трейсбеком
            import traceback
            error_trace = traceback.format_exc()
            logger.error(f"КРИТИЧЕСКАЯ ОШИБКА в handle_message: {type(e).__name__}: {e}")
            logger.error(f"Трассировка ошибки:\n{error_trace}")
            logger.error(f"Сообщение вызвавшее ошибку: '{message_text}'")
            logger.error(f"User ID: {user_id}, Username: {update.effective_user.username}")

            # Пытаемся дать более информативный ответ
            try:
                await update.message.reply_text(
                    "Произошла техническая ошибка при обработке вашего сообщения.\n"
                    "Пожалуйста, опишите проблему другими словами или попробуйте позже.\n\n"
                    "Если проблема повторится, пожалуйста, напишите: 'связь с диспетчером'"
                )
            except Exception as reply_error:
                logger.error(f"Не удалось отправить ответ об ошибке: {reply_error}")
                # Пытаемся отправить максимально простой ответ
                try:
                    await update.message.reply_text("Произошла ошибка. Попробуйте еще раз.")
                except Exception as final_error:
                    logger.error(f"Полная неспособность отправить ответ: {final_error}")

    async def _handle_main_agent_success(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """
        Обработка успешного результата от MainAgent

        ИСПРАВЛЕНО: Приоритет result.message над needs_confirmation
        ИСПРАВЛЕНО: Возвращает текст ответа для сохранения в истории
        """
        try:
            service_id = result['service_id']
            service_name = result['service_name']

            # ИСПРАВЛЕНО: ПРиОРИТЕТ: Если есть message - используем его (уточняющий вопрос от MainAgent)
            if 'message' in result and result['message']:
                message_text = result['message']
                await update.message.reply_text(message_text.strip())
                return message_text.strip()

            # Если нужно подтверждение
            if result.get('needs_confirmation', False):
                confirmation_text = f"Я определил, что у вас проблема: {service_name}\n\nЭто правильно?"
                await update.message.reply_text(confirmation_text.strip())
                return confirmation_text.strip()
            else:
                # Сразу создаем заявку
                ticket_text = await self._create_service_ticket(update, service_id, service_name, result, dialog)
                return ticket_text or f"Заявка создана: {service_name}"

        except Exception as e:
            logger.error(f"Ошибка в _handle_main_agent_success: {e}")
            await update.message.reply_text("Ошибка при обработке результата")
            return "Ошибка при обработке результата"

    async def _handle_main_agent_ambiguous(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """
        Обработка неопределенного результата от MainAgent

        ИСПРАВЛЕНО: Возвращает текст ответа для сохранения в истории
        """
        try:
            candidates = result.get('candidates', [])
            candidate_names = result.get('candidate_names', [])
            needs_clarification = result.get('needs_clarification', False)
            message = result.get('message', '')

            # Приоритет 1: Если есть уточняющее сообщение от MainAgent - используем его
            if needs_clarification and message:
                await update.message.reply_text(message.strip())
                return message.strip()
            # Приоритет 2: Если есть кандидаты - предлагаем выбор
            elif candidates:
                clarification_text = message if message else 'Найдено несколько вариантов:'
                clarification = f"""
{clarification_text}

Пожалуйста, уточните, что именно у вас:
{chr(10).join([f'• {name}' for name in candidate_names])}
"""
                await update.message.reply_text(clarification.strip())
                return clarification.strip()
            # Приоритет 3: Стандартный запрос уточнения (без эмодзи)
            else:
                fallback_text = "Я не совсем понял, о чем речь. Пожалуйста, расскажите подробнее, что у вас случилось."
                await update.message.reply_text(fallback_text)
                return fallback_text

        except Exception as e:
            logger.error(f"Ошибка в _handle_main_agent_ambiguous: {e}")
            await update.message.reply_text("Ошибка при анализе запроса")
            return "Ошибка при анализе запроса"

    async def _handle_main_agent_error(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """
        Обработка ошибки от MainAgent

        ИСПРАВЛЕНО: Возвращает текст ответа для сохранения в истории
        """
        try:
            error_message = result.get('error', 'Неизвестная ошибка')
            user_message = result.get('message', 'Произошла ошибка. Попробуйте еще раз.')

            logger.error(f"MainAgent error: {error_message}")
            await update.message.reply_text(user_message)
            return user_message

        except Exception as e:
            logger.error(f"Ошибка в _handle_main_agent_error: {e}")
            fallback_msg = "Произошла ошибка. Попробуйте еще раз."
            await update.message.reply_text(fallback_msg)
            return fallback_msg

    async def _handle_main_agent_unclear(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """
        Обработка неясного результата от MainAgent

        ИСПРАВЛЕНО: Возвращает текст ответа для сохранения в истории
        """
        try:
            fallback_text = "Я не совсем понял, о чем речь. Пожалуйста, расскажите подробнее, что у вас случилось."
            await update.message.reply_text(fallback_text)
            return fallback_text
        except Exception as e:
            logger.error(f"Ошибка в _handle_main_agent_unclear: {e}")
            await update.message.reply_text("Ошибка. Попробуйте еще раз.")
            return "Ошибка. Попробуйте еще раз."

    async def _create_service_ticket(self, update: Update, service_id: int, service_name: str,
                                    result: dict, dialog: DialogMemoryManager):
        """
        Создание заявки на услугу с новым форматом JSON

        ИСПРАВЛЕНО: Возвращает текст ответа для сохранения в истории
        ИСПРАВЛЕНО: Использует правильный ключ 'text' вместо 'message' в dialog_history
        """
        try:
            # Определяем объект обслуживания
            dialog_history = dialog.conversation_history
            current_message = update.message.text if update.message else ""

            object_detection = await self.object_detector.detect_service_object(
                current_message,
                [msg.get('text', '') for msg in dialog_history if msg.get('role') == 'user']
            )

            # Формируем полный текст обращения
            all_user_messages = [
                msg.get('text', '') for msg in dialog_history
                if msg.get('role') == 'user'
            ] + [current_message]
            complaint_text = '. '.join(filter(None, all_user_messages))

            # Создаем финальный JSON в соответствии с мини-ТЗ
            final_json = self.json_formatter.create_final_json(
                service_id=service_id,
                confidence=result.get('confidence', 0.8),
                complaint_text=complaint_text,
                object_id=object_detection.get('object_id'),
                scope=object_detection.get('scope', 'COMMON')
            )

            # Валидация JSON
            if not self.json_formatter.validate_final_json(final_json):
                logger.error(f"JSON не прошел валидацию: {final_json}")
                await update.message.reply_text("Ошибка при формировании заявки")
                return "Ошибка при формировании заявки"

            # Отправляем валидный JSON (одно сообщение, строго валидный JSON)
            json_response = self.json_formatter.format_for_telegram(final_json)
            await update.message.reply_text(json_response)

            # Логируем для отладки
            logger.info(f"Отправлен финальный JSON: {json_response}")

            return json_response

        except Exception as e:
            logger.error(f"Ошибка в _create_service_ticket: {e}")
            await update.message.reply_text("Ошибка при создании заявки")
            return "Ошибка при создании заявки"

    async def _handle_success_result(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """Обработка успешного результата"""
        try:
            # Создаем финальный JSON (обернуто в sync_to_async)
            @sync_to_async
            def create_output_json_sync():
                return self.orchestrator.create_output_json(
                    service_id=result['service_id'],
                    service_name=result['service_name'],
                    service_confidence=result.get('confidence', 0.8),
                    address_components=result['address_components'],
                    user_name=dialog.user_name,
                    user_phone=None,  # Можно добавить позже
                    description=result['user_message'],
                    trace_id=result.get('trace_id')
                )

            output_json = await create_output_json_sync()

            # Сохраняем заявку в БД (обернуто в sync_to_async)
            @sync_to_async
            def save_ticket_sync():
                return self.orchestrator.save_final_ticket(output_json, dialog.dialog_id)

            ticket_id = await save_ticket_sync()

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
            await update.message.reply_text("Ошибка при создании заявки")

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
Понял проблему: {result.get('service_name', 'проблема')}

Адрес: {current_address if current_address else 'Еще не определен'}

{missing_info}

Отправьте недостающую информацию и я продолжу помогать.
            """

            await update.message.reply_text(response_text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ошибка в _handle_need_address: {e}")

    def _get_missing_address_info(self, dialog: DialogMemoryManager) -> str:
        """Определить, какой информации об адресе не хватает"""
        missing = []

        if not dialog.extracted_entities.get('street'):
            missing.append("Улицу")

        if not dialog.extracted_entities.get('house_number'):
            missing.append("Номер дома")

        if not dialog.extracted_entities.get('apartment_number'):
            missing.append("Номер квартиры (если есть)")

        if missing:
            return f"**Нужно уточнить**: {', '.join(missing)}"

        return "Адрес определен. Можно создавать заявку."

    async def _handle_spam_result(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """Обработка спама"""
        category = result.get('category', 'SPAM')

        if category == 'PROFANITY':
            response = "Сообщение содержит нецензурную лексику.\n\nПожалуйста, ведите себя уважительно."
        elif category == 'NON_CONSTRUCTIVE':
            response = "Не удалось определить конструктивное содержание.\n\nПопробуйте более четко описать вашу проблему."
        elif category == 'VAGUE':
            response = "Сообщение слишком расплывчатое.\n\nПожалуйста, опишите проблему подробнее."
        else:
            response = "Сообщение определено как спам.\n\nПопробуйте еще раз с другим текстом."

        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_reject_result(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """Обработка отклонения"""
        response = f"""
Не удалось обработать сообщение

Причина: {result.get('reason', 'неизвестна')}

Попробуйте:
- Описать проблему более четко
- Указать полный адрес
- Избегать сложных формулировок

Пример: "Течет кран на кухне по адресу ул. Ленина, дом 15, квартира 42"
        """

        await update.message.reply_text(response, parse_mode='Markdown')

    async def _handle_unclear_result(self, update: Update, result: dict, dialog: DialogMemoryManager):
        """Обработка неясного результата"""
        # Получаем исходное сообщение из диалога
        original_message = dialog.get_last_message_text() if dialog else "Неизвестно"

        # Используем улучшенный промпт для запроса уточнения
        clarification_template = prompt_manager.get_clarification_template()
        response = prompt_manager.format_clarification_message(original_message, clarification_template)

        await update.message.reply_text(response, parse_mode='Markdown')

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий на кнопки"""
        try:
            query = update.callback_query
            await query.answer()

            if query.data == "confirm_yes":
                # Подтверждение заявки
                await query.edit_message_text(
                    "Заявка подтверждена и отправлена в работу.\n\n"
                    "Мы свяжемся с вами в ближайшее время.\n"
                    "Благодарим за обращение.",
                    parse_mode='Markdown'
                )
                logger.info(f"Пользователь {update.effective_user.id} подтвердил заявку")

            elif query.data == "confirm_no":
                # Отмена заявки
                await query.edit_message_text(
                    "Заявка отменена.\n\n"
                    "Если хотите создать новую - опишите проблему заново.",
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

    logger.info("Бот Сигизмунд Лазоревич запускается")

    # Запускаем бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()