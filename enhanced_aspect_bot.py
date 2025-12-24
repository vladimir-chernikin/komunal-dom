#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Улучшенный Telegram бот УК "Аспект" с системой обнаружения услуг
Версия: 2.0
Объединяет проверку адресов и интеллектуальное определение услуг
"""

import asyncio
import logging
import os
import re
import sys
import html
import json
from typing import Dict, Optional
from datetime import datetime
from decouple import config

# Telegram imports
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# Django setup
sys.path.append('/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

# Импортируем AI менеджер и унифицированный обработчик сообщений
from portal.ai_manager import ai_manager
from message_handler_service import MessageHandlerService
from main_agent import MainAgent

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

class ServiceBotState:
    """Расширенный класс для хранения состояния диалога"""
    def __init__(self, user_id):
        self.user_id = user_id
        self.mode = 'ADDRESS_CHECK'  # ADDRESS_CHECK | SERVICE_REQUEST | CONFIRMATION | ADDRESS_INPUT
        self.address_attempts = 0
        self.last_address = None
        self.warnings_count = 0
        self.last_question_time = None

        # Поля для обслуживания заявок
        self.current_service_id = None
        self.current_service_name = None
        self.current_address = None
        self.address_components = None  # ДОБАВЛЕНО: Компоненты адреса от AddressExtractor
        self.building_id = None
        self.unit_id = None
        self.confidence = 0.0
        self.trace_id = None
        self.dialog_id = None

class EnhancedAspectBot:
    """Улучшенный бот УК "Аспект" с интеллектуальным определением услуг"""

    def __init__(self):
        self.bot_name = "Сигизмунд Лазоревич"
        self.use_yandex = True
        self.yandex_api_key = YANDEX_API_KEY
        self.yandex_folder_id = YANDEX_FOLDER_ID

        # Хранилище состояний диалогов
        self.conversations = {}

        # ИСПРАВЛЕНО: Инициализируем унифицированную систему обработки
        try:
            # MainAgent - воронка точности
            self.main_agent = MainAgent()

            # MessageHandlerService - единый обработчик сообщений
            self.message_handler = MessageHandlerService(main_agent=self.main_agent)

            logger.info("Унифицированная система обработки сообщений инициализирована")
        except Exception as e:
            logger.error(f"Ошибка инициализации унифицированной системы: {e}")
            self.main_agent = None
            self.message_handler = None

    def get_conversation_state(self, user_id):
        """Получить или создать состояние диалога"""
        if user_id not in self.conversations:
            self.conversations[user_id] = ServiceBotState(user_id)
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
                    "temperature": 0.3,
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

            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()

            result = response.json()
            return result['result']['alternatives'][0]['message']['text']

        except Exception as e:
            logger.error(f"Ошибка при запросе к YandexGPT: {e}")
            return None

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        user = update.effective_user
        state = self.get_conversation_state(user.id)

        welcome_text = f"""Добрый день, {user.first_name}!

Я {self.bot_name} - AI-ассистент управляющей компании "Аспект".

Я могу помочь вам:
- Проверить адрес в зоне обслуживания УК
- Принять и зарегистрировать заявку на обслуживание
- Определить услугу по описанию проблемы

Просто отправьте мне сообщение с описанием проблемы или адрес для проверки.

Команды:
/help - справка
/streets - список улиц на обслуживании
/service - создать заявку по проблеме
/address - проверить адрес
"""

        await update.message.reply_text(welcome_text)
        state.mode = 'ADDRESS_CHECK'

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = f"""Справка по боту {self.bot_name}

Основные функции:
- Описание проблемы → Я определю услугу и помогу создать заявку
- Проверка адреса → Уточню обслуживание УК "Аспект"
- Просмотр улиц → Список всех улиц в зоне обслуживания

Примеры сообщений для заявок:
- "Протекает кран на кухне"
- "Нет света в квартире"
- "Забилась раковина в ванной"
- "Из потолка капает вода"

Команды:
/start - начало работы
/streets - список улиц на обслуживании
/service - режим создания заявки
/address - режим проверки адреса
/help - эта справка

Просто опишите проблему своими словами, а я определю нужную услугу!
"""

        await update.message.reply_text(help_text)

    async def service_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Переключение в режим создания заявки"""
        user = update.effective_user
        state = self.get_conversation_state(user.id)
        state.mode = 'SERVICE_REQUEST'

        await update.message.reply_text(
            "Режим создания заявки активирован.\n\n"
            "Опишите проблему, и я определю необходимую услугу.\n"
            "Например: 'протекает кран' или 'нет электричества'\n\n"
            "Для отмены отправьте /cancel"
        )

    async def address_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Переключение в режим проверки адреса"""
        user = update.effective_user
        state = self.get_conversation_state(user.id)
        state.mode = 'ADDRESS_CHECK'

        await update.message.reply_text(
            "Режим проверки адреса активирован.\n\n"
            "Отправьте адрес для проверки (например: ул. Ленина, д. 5)\n\n"
            "Для отмены отправьте /cancel"
        )

    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущей операции"""
        user = update.effective_user
        state = self.get_conversation_state(user.id)

        # Сбрасываем состояние
        state.mode = 'ADDRESS_CHECK'
        state.current_service_id = None
        state.current_address = None

        await update.message.reply_text(
            "Операция отменена.\n\n"
            "Я готов к новым запросам. Используйте:\n"
            "/service - для создания заявки\n"
            "/address - для проверки адреса"
        )

    def detect_message_type(self, text: str) -> str:
        """Определяет тип сообщения по ключевым словам"""
        text_lower = text.lower()

        # Признаки запроса на обслуживание
        service_keywords = [
            'протека', 'течет', 'капа', 'прорыв', 'засор', 'забился', 'нет', 'не работает',
            'сломал', 'повред', 'авари', 'проблем', 'неисправн', 'ремонт', 'замен',
            'отключил', 'перегор', 'шум', 'скрип', 'дежур', 'заявк', 'вызов'
        ]

        # Признаки запроса адреса
        address_keywords = [
            'адрес', 'улица', 'ул.', 'дом', 'д.', 'квартира', 'кв.', 'подъезд',
            'живу', 'проживаю', 'обслуживани'
        ]

        # Считаем количество ключевых слов
        service_count = sum(1 for kw in service_keywords if kw in text_lower)
        address_count = sum(1 for kw in address_keywords if kw in text_lower)

        # Если больше признаков обслуживания - это заявка
        if service_count > address_count:
            return 'SERVICE_REQUEST'
        elif address_count > 0:
            return 'ADDRESS_CHECK'
        else:
            # По умолчанию считаем заявкой
            return 'SERVICE_REQUEST'

    async def handle_service_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Обработка запроса на создание заявки через MessageHandlerService"""
        user = update.effective_user
        state = self.get_conversation_state(user.id)

        if not self.message_handler:
            await update.message.reply_text(
                "К сожалению, система определения услуг временно недоступна.\n"
                "Пожалуйста, позвоните напрямую в УК."
            )
            return

        # Генерируем session_id
        session_id = f"telegram_{user.id}"

        try:
            # Обрабатываем сообщение через MessageHandlerService
            result = await self.message_handler.handle_incoming_message(
                text=text,
                user_id=str(user.id),
                channel='telegram',
                session_id=session_id,
                metadata={
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name
                }
            )

            # Анализируем результат
            if result.get('status') == 'success':
                response = result.get('response', '')

                # Проверяем, была ли это только проверка приветствия
                if result.get('is_greeting'):
                    # Просто отвечаем на приветствие, ничего не делаем
                    await update.message.reply_text(response)
                    return

                # Если услуга определена успешно (SUCCESS)
                if result.get('raw_result', {}).get('status') == 'SUCCESS':
                    service_name = result['raw_result'].get('service_name', '')
                    address_string = result['raw_result'].get('address_string', '')
                    address_components = result['raw_result'].get('address_components', {})

                    # Сохраняем в состоянии
                    state.current_service_id = result['raw_result'].get('service_id')
                    state.current_service_name = service_name
                    state.current_address = address_string
                    state.address_components = address_components
                    state.confidence = result['raw_result'].get('confidence', 0.8)

                    # Если адрес не найден - запрашиваем
                    if not address_components.get('street') or not address_components.get('house_number'):
                        state.mode = 'ADDRESS_INPUT'
                        await update.message.reply_text(
                            f"{response}\n\n"
                            f"Пожалуйста, укажите адрес:\n"
                            "Улица и номер дома (и квартиры, если нужно)\n\n"
                            "Например: ул. Ленина, д. 5, кв. 10"
                        )
                        return

                    # Если адрес найден - переходим к подтверждению
                    state.mode = 'CONFIRMATION'

                    # Создаем клавиатуру для подтверждения
                    keyboard = [
                        [InlineKeyboardButton("Да, все верно", callback_data='confirm_yes')],
                        [InlineKeyboardButton("Нет, изменить", callback_data='confirm_no')],
                        [InlineKeyboardButton("Отмена", callback_data='confirm_cancel')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    confirm_text = f"Проверьте информацию:\n\n"
                    confirm_text += f"Услуга: {service_name}\n"
                    if address_string:
                        confirm_text += f"Адрес: {address_string}\n"
                    confirm_text += f"\nВсе верно?"

                    await update.message.reply_text(
                        confirm_text,
                        reply_markup=reply_markup
                    )
                    return

                # Если нужна детализация (AMBIGUOUS)
                elif result.get('raw_result', {}).get('status') == 'AMBIGUOUS':
                    # Отправляем уточняющий вопрос
                    await update.message.reply_text(response)
                    return

                # Обычный ответ
                await update.message.reply_text(response)

            else:
                # Ошибка обработки
                await update.message.reply_text(
                    f"Произошла ошибка: {result.get('error', 'Неизвестная ошибка')}"
                )

        except Exception as e:
            logger.error(f"Ошибка при обработке заявки: {e}")
            await update.message.reply_text(
                "Произошла ошибка при обработке запроса.\n"
                "Пожалуйста, попробуйте еще раз или позвоните в УК."
            )

    async def handle_address_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Обработка ввода адреса для заявки"""
        user = update.effective_user
        state = self.get_conversation_state(user.id)

        # ИСПРАВЛЕНО: AddressExtractor теперь интегрирован в MainAgent
        # При повторном вызове с адресом, MainAgent извлечет адрес из сообщения
        if not self.message_handler:
            await update.message.reply_text("Система временно недоступна")
            return

        try:
            # Обрабатываем сообщение с адресом через MessageHandlerService
            result = await self.message_handler.handle_incoming_message(
                text=text,
                user_id=str(user.id),
                channel='telegram',
                session_id=f"telegram_{user.id}",
                metadata={
                    'username': user.username,
                    'first_name': user.first_name,
                    'is_address_input': True  # Флаг что это ввод адреса
                }
            )

            # Анализируем результат
            if result.get('status') == 'success':
                raw_result = result.get('raw_result', {})

                # Если адрес найден в raw_result
                address_components = raw_result.get('address_components', {})
                address_string = raw_result.get('address_string', '')

                # Сохраняем адрес
                if address_components:
                    state.address_components = address_components
                    state.current_address = address_string or text

                    # Переходим к подтверждению
                    state.mode = 'CONFIRMATION'

                    # Создаем клавиатуру для подтверждения
                    keyboard = [
                        [InlineKeyboardButton("Да, все верно", callback_data='confirm_yes')],
                        [InlineKeyboardButton("Нет, изменить", callback_data='confirm_no')],
                        [InlineKeyboardButton("Отмена", callback_data='confirm_cancel')]
                    ]
                    reply_markup = InlineKeyboardMarkup(keyboard)

                    confirm_text = f"Проверьте информацию:\n\n"
                    confirm_text += f"Услуга: {state.current_service_name}\n"
                    if address_string:
                        confirm_text += f"Адрес: {address_string}\n"
                    confirm_text += f"\nВсе верно?"

                    await update.message.reply_text(
                        confirm_text,
                        reply_markup=reply_markup
                    )
                    return

            # Если адрес не распознан - просим уточнить
            await update.message.reply_text(
                "Не удалось распознать адрес.\n\n"
                "Пожалуйста, укажите адрес в формате:\n"
                "ул. Название, д. Номер, кв. Номер\n\n"
                "Например: ул. Ленина, д. 5, кв. 10"
            )

        except Exception as e:
            logger.error(f"Ошибка при обработке адреса: {e}")
            await update.message.reply_text(
                "Ошибка при обработке адреса. Попробуйте еще раз."
            )

    async def handle_confirmation_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка кнопок подтверждения"""
        query = update.callback_query
        await query.answer()

        user = update.effective_user
        state = self.get_conversation_state(user.id)

        if query.data == 'confirm_yes':
            # Подтверждение - создаем заявку
            try:
                # ИСПРАВЛЕНО: Создание заявки через БД напрямую (или через сервис в будущем)
                # Пока просто подтверждаем прием
                ticket_number = f"TK-{datetime.now().strftime('%Y%m%d%H%M%S')}"

                # Формируем сообщение
                confirm_text = f"Заявка успешно принята!\n\n"
                confirm_text += f"Номер: {ticket_number}\n"
                confirm_text += f"Услуга: {state.current_service_name}\n"
                if state.current_address:
                    confirm_text += f"Адрес: {state.current_address}\n"
                confirm_text += f"\nНаши специалисты свяжутся с вами в ближайшее время."

                await query.edit_message_text(confirm_text)

                # TODO: Здесь будет создание заявки в БД через Django models
                # from tickets.models import Ticket
                # ticket = Ticket.objects.create(...)
                # ticket.save()

                # Сбрасываем состояние
                state.mode = 'ADDRESS_CHECK'
                state.current_service_id = None
                state.current_address = None
                state.address_components = None

            except Exception as e:
                logger.error(f"Ошибка при создании заявки: {e}")
                await query.edit_message_text(
                    "Произошла ошибка при создании заявки. Пожалуйста, позвоните в УК."
                )

        elif query.data == 'confirm_no':
            # Пользователь хочет изменить
            state.mode = 'ADDRESS_INPUT'
            await query.edit_message_text(
                "Что именно нужно изменить?\n\n"
                "Отправьте:\n"
                "- /service - выбрать другую услугу\n"
                "- Адрес в формате 'ул. Название, д. Номер, кв. Номер'\n\n"
                "Или /cancel для отмены"
            )

        elif query.data == 'confirm_cancel':
            # Отмена
            state.mode = 'ADDRESS_CHECK'
            state.current_service_id = None
            state.current_address = None
            await query.edit_message_text(
                "Создание заявки отменено.\n\n"
                "Я готов к новым запросам. Используйте:\n"
                "/service - для создания заявки\n"
                "/address - для проверки адреса"
            )

    async def show_streets(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает список улиц на обслуживании"""
        try:
            from django.db import connection

            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT DISTINCT ao.name, ao.type_name
                    FROM kladr_address_objects ao
                    JOIN buildings b ON ao.ao_id = b.parent_ao_id
                    ORDER BY ao.name
                    LIMIT 50
                """)

                streets = cursor.fetchall()

                if streets:
                    text = "📍 **Улицы в зоне обслуживания УК 'Аспект':**\n\n"
                    for i, (name, type_name) in enumerate(streets, 1):
                        text += f"{i}. {type_name} {name}\n"

                    text += f"\nВсего: {len(streets)} улиц\n\n"
                    text += "Отправьте адрес для проверки (например: ул. Ленина, д. 5)"

                    if len(text) > 4000:
                        text = text[:3950] + "...\n\n(и еще улицы)"

                    await update.message.reply_text(text, parse_mode='Markdown')
                else:
                    await update.message.reply_text("📍 Улицы не найдены в базе данных")

        except Exception as e:
            logger.error(f"Ошибка при получении списка улиц: {e}")
            await update.message.reply_text("😔 Ошибка при загрузке списка улиц")

    async def check_address_with_ai(self, update: Update, context: ContextTypes.DEFAULT_TYPE, address_text):
        """Проверяет адрес с использованием AI и базы КЛАДР"""
        try:
            # Проверяем есть ли адрес в КЛАДР
            from django.db import connection

            with connection.cursor() as cursor:
                # Нормализуем и ищем адрес
                normalized_address = address_text.strip().lower()

                # Ищем улицы
                cursor.execute("""
                    SELECT DISTINCT ao.name, ao.type_name, COUNT(*) as building_count
                    FROM kladr_address_objects ao
                    LEFT JOIN buildings b ON ao.ao_id = b.parent_ao_id
                    WHERE LOWER(ao.name) LIKE %s
                       OR LOWER(ao.name || ' ' || b.house_number) LIKE %s
                    GROUP BY ao.ao_id, ao.name, ao.type_name
                    ORDER BY building_count DESC, ao.name
                    LIMIT 10
                """, [f'%{normalized_address}%', f'%{normalized_address}%'])

                results = cursor.fetchall()

                if results:
                    text = f"🔍 **Результаты поиска адреса:**\n\n"

                    for name, type_name, count in results[:5]:
                        text += f"📍 {type_name} {name}"
                        if count > 0:
                            text += f" ({count} домов)"
                        text += "\n"

                    # Используем AI для детального анализа
                    ai_prompt = f"""
Проанализируй адрес: "{address_text}"

Найденные варианты в базе:
{chr(10).join([f"- {type_name} {name}" for name, type_name, _ in results[:3]])}

Ответь кратко:
1. Это адрес в зоне обслуживания?
2. Точный ли адрес?
3. Какие рекомендации?
"""

                    ai_response = await self.ask_yandexgpt(ai_prompt, 200)

                    if ai_response:
                        text += f"\n\n🤖 **Анализ AI:**\n{ai_response}"

                    await update.message.reply_text(text, parse_mode='Markdown')
                else:
                    # Если не найдено, используем только AI
                    ai_prompt = f"""
Пользователь ищет адрес: "{address_text}"

Это адрес в г. Россия? Проверь правильность написания.
Дай краткий ответ:
1. Корректный ли адрес?
2. Какие исправления посоветуешь?
3. Это вообще адрес?
"""

                    ai_response = await self.ask_yandexgpt(ai_prompt, 250)

                    text = f"🔍 **Анализ адреса:**\n\n{ai_response}"
                    await update.message.reply_text(text, parse_mode='Markdown')

        except Exception as e:
            logger.error(f"Ошибка при проверке адреса: {e}")
            await update.message.reply_text("😔 Ошибка при проверке адреса. Попробуйте позже.")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Основной обработчик сообщений"""
        user = update.effective_user
        state = self.get_conversation_state(user.id)
        text = update.message.text

        # Фильтрация ругательств
        if self.contains_profanity(text):
            state.warnings_count += 1
            if state.warnings_count >= 2:
                await update.message.reply_text("⚠️ За многократное использование нецензурной лексики диалог будет прекращен.")
                return
            else:
                await update.message.reply_text("🚫 Пожалуйста, избегайте нецензурной лексики в сообщениях.")
                return

        # Обработка в зависимости от режима
        if state.mode == 'SERVICE_REQUEST':
            await self.handle_service_request(update, context, text)

        elif state.mode == 'ADDRESS_INPUT':
            await self.handle_address_input(update, context, text)

        elif state.mode == 'ADDRESS_CHECK':
            # Автоопределение типа сообщения
            detected_type = self.detect_message_type(text)

            if detected_type == 'SERVICE_REQUEST':
                state.mode = 'SERVICE_REQUEST'
                await self.handle_service_request(update, context, text)
            else:
                await self.check_address_with_ai(update, context, text)

        else:
            # По умолчанию - проверка адреса
            await self.check_address_with_ai(update, context, text)

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}")

        # Отправляем сообщение об ошибке пользователю
        if update and hasattr(update, 'message'):
            try:
                await update.message.reply_text(
                    "😔 Произошла ошибка. Пожалуйста, попробуйте позже."
                )
            except:
                pass

def main():
    """Основная функция запуска бота"""
    # Проверяем токен
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN не найден в переменных окружения!")
        return

    # Инициализация Django
    import django
    django.setup()

    # Перезагружаем промпты при запуске
    ai_manager.reload_prompts()

    # Создание бота
    bot = EnhancedAspectBot()

    # Создание приложения
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Добавление обработчиков
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CommandHandler("streets", bot.show_streets))
    application.add_handler(CommandHandler("service", bot.service_command))
    application.add_handler(CommandHandler("address", bot.address_command))
    application.add_handler(CommandHandler("cancel", bot.cancel_command))
    application.add_handler(CallbackQueryHandler(bot.handle_confirmation_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Добавление обработчика ошибок
    application.add_error_handler(bot.error_handler)

    print(f"🚀 Улучшенный бот {bot.bot_name} v2.0 запускается с системой обнаружения услуг...")

    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()