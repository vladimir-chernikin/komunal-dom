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
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
        self.session_id = None  # ИСПРАВЛЕНО (2026-01-05): Текущая сессия для логирования outbound

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

    async def _reply_and_log(
        self,
        update: Update,
        text: str,
        session_id: str = None,
        metadata: Dict = None
    ):
        """
        Отправляет ответ пользователю И логирует outbound сообщение

        ИСПРАВЛЕНО (2026-01-05):
        - Логирует все Bot -> User сообщения в dialog_logs
        - Это нужно для трассировки и accumulation txtPrb

        Args:
            update: Telegram Update объект
            text: Текст ответа
            session_id: ID сессии (берется из state если не передан)
            metadata: Метаданные для логирования (txtPrb, filters, etc)
        """
        user = update.effective_user
        state = self.get_conversation_state(user.id)

        # Получаем session_id из state если не передан
        if not session_id:
            session_id = state.session_id

        # Отправляем ответ пользователю
        await update.message.reply_text(text)

        # Логируем outbound сообщение
        if self.message_handler and session_id:
            try:
                await self.message_handler.log_outbound_message(
                    text=text,
                    user_id=str(user.id),
                    channel='telegram',
                    session_id=session_id,
                    metadata=metadata or {}
                )
            except Exception as e:
                logger.error(f"Ошибка логирования outbound сообщения: {e}")

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
        """
        Определяет тип сообщения

        ИСПРАВЛЕНО (2025-12-25): Удален хардкод keywords
        Теперь всегда считаем SERVICE_REQUEST - пусть MainAgent разбирается
        """
        # УДАЛЕНО: Весь хардкод service_keywords и address_keywords
        # FilterDetectionService и MainAgent должны определять что нужно пользователю

        # Всегда считаем заявкой на обслуживание
        # Если пользователь хочет проверить адрес - он скажет об этом явно
        return 'SERVICE_REQUEST'

    async def handle_service_request(self, update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
        """Обработка запроса на создание заявки через MessageHandlerService"""
        user = update.effective_user
        state = self.get_conversation_state(user.id)

        # ИСПРАВЛЕНО: Обработка "нет", "неправильно" для режима CONFIRMATION
        if state.mode == 'CONFIRMATION':
            text_lower = text.lower().strip()
            # Слова отмены/отказа
            denial_words = ['нет', 'неправ', 'не та', 'другая', 'не то', 'ошиб', 'неверно']
            if any(word in text_lower for word in denial_words):
                # ИСПРАВЛЕНО (2025-12-25): Умный вопрос от AI агента вместо хардкода
                state.mode = 'ADDRESS_CHECK'
                state.current_service_id = None
                state.current_service_name = None
                state.current_address = None
                state.address_components = None

                # ИСПРАВЛЕНО (2025-12-25): Используем AI агента для умного вопроса
                clarification = await self._ask_ai_clarification(text, state)

                # ИСПРАВЛЕНО (2026-01-05): Логируем outbound
                await self._reply_and_log(update, clarification, state.session_id)
                return

        if not self.message_handler:
            await self._reply_and_log(
                update,
                "К сожалению, система определения услуг временно недоступна.\n"
                "Пожалуйста, позвоните напрямую в УК.",
                state.session_id
            )
            return

        # ИСПРАВЛЕНО (2025-12-28): НЕ передаем фиксированный session_id
        # Позволяем MessageHandlerService создать новую сессию для приветствия
        # или продолжить существующую сессию
        try:
            # Обрабатываем сообщение через MessageHandlerService
            result = await self.message_handler.handle_incoming_message(
                text=text,
                user_id=str(user.id),
                channel='telegram',
                session_id=None,  # ИСПРАВЛЕНО: None = автоматическое управление сессиями
                metadata={
                    'username': user.username,
                    'first_name': user.first_name,
                    'last_name': user.last_name
                }
            )

            # ИСПРАВЛЕНО (2026-01-05): Сохраняем session_id для логирования outbound
            session_id = result.get('session_id')
            if session_id:
                state.session_id = session_id
                logger.info(f"✅ Session ID сохранен в state: {session_id}")

            # Анализируем результат
            if result.get('status') == 'success':
                response = result.get('response', '')

                # Проверяем, была ли это только проверка приветствия
                if result.get('is_greeting'):
                    # Просто отвечаем на приветствие, ничего не делаем
                    await self._reply_and_log(update, response, session_id)
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

                    # ИСПРАВЛЕНО (2025-12-25): ИСПОЛЬЗУЕМ сообщение от MainAgent!
                    # КРИТИЧЕСКИ ВАЖНО: НЕ добавлять "Ответьте да или нет" - это закрытый вопрос!
                    # КРИТИЧЕСКИ ВАЖНО: НЕ добавлять "опишите проблему другими словами" - запрещенная фраза!
                    state.mode = 'CONFIRMATION'

                    # Используем ИЗНАЧАЛЬНОЕ сообщение от MainAgent (без изменений!)
                    confirm_text = result['raw_result'].get('message', f"Правильно ли я понял, что у вас: {service_name}?")

                    # ИСПРАВЛЕНО (2026-01-06): Объединяем _metadata и _ai_metadata
                    raw_result = result.get('raw_result', {})
                    metadata = raw_result.get('_metadata', {})
                    ai_metadata = raw_result.get('_ai_metadata', {})

                    # Если есть _ai_metadata - добавляем к metadata
                    if ai_metadata:
                        metadata = {**metadata, **ai_metadata}

                    await self._reply_and_log(update, confirm_text, session_id, metadata)
                    return

                # Если нужна детализация (AMBIGUOUS)
                elif result.get('raw_result', {}).get('status') == 'AMBIGUOUS':
                    # ИСПРАВЛЕНО (2026-01-06): Объединяем _metadata и _ai_metadata
                    raw_result = result.get('raw_result', {})
                    metadata = raw_result.get('_metadata', {})
                    ai_metadata = raw_result.get('_ai_metadata', {})

                    # Если есть _ai_metadata - добавляем к metadata
                    if ai_metadata:
                        metadata = {**metadata, **ai_metadata}

                    await self._reply_and_log(update, response, session_id, metadata)
                    return

                # Обычный ответ
                # ИСПРАВЛЕНО (2026-01-06): Добавляем metadata для всех ответов
                metadata = result.get('raw_result', {}).get('_metadata', {})
                await self._reply_and_log(update, response, session_id, metadata)

            else:
                # Ошибка обработки
                await self._reply_and_log(
                    update,
                    f"Произошла ошибка: {result.get('error', 'Неизвестная ошибка')}",
                    state.session_id
                )

        except Exception as e:
            logger.error(f"Ошибка при обработке заявки: {e}")
            await self._reply_and_log(
                update,
                "Произошла ошибка при обработке запроса.\n"
                "Пожалуйста, попробуйте еще раз или позвоните в УК.",
                state.session_id
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

                    # ИСПРАВЛЕНО (2025-12-25): Голосовой интерфейс - открытые вопросы!
                    # КРИТИЧЕСКИ ВАЖНО: НЕ добавлять "Ответьте да или нет" - это закрытый вопрос!
                    confirm_text = f"Проверьте информацию:\n\n"
                    confirm_text += f"Услуга: {state.current_service_name}\n"
                    if address_string:
                        confirm_text += f"Адрес: {address_string}\n"
                    confirm_text += f"\nВсе верно?"

                    await update.message.reply_text(confirm_text)
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

    async def finalize_application(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Финализация заявки - создание в БД и подтверждение пользователю"""
        user = update.effective_user
        state = self.get_conversation_state(user.id)

        try:
            # Создание заявки через БД (или через сервис в будущем)
            # Пока просто подтверждаем прием
            ticket_number = f"TK-{datetime.now().strftime('%Y%m%d%H%M%S')}"

            # Формируем сообщение
            confirm_text = f"Заявка успешно принята!\n\n"
            confirm_text += f"Номер: {ticket_number}\n"
            confirm_text += f"Услуга: {state.current_service_name}\n"
            if state.current_address:
                confirm_text += f"Адрес: {state.current_address}\n"
            confirm_text += f"\nНаши специалисты свяжутся с вами в ближайшее время."

            await update.message.reply_text(confirm_text)

            # TODO: Здесь будет создание заявки в БД через Django models
            # from tickets.models import Ticket
            # ticket = Ticket.objects.create(...)
            # ticket.save()

            # Сбрасываем состояние
            state.mode = 'ADDRESS_CHECK'
            state.current_service_id = None
            state.current_service_name = None
            state.current_address = None
            state.address_components = None

        except Exception as e:
            logger.error(f"Ошибка при создании заявки: {e}")
            await update.message.reply_text(
                "Произошла ошибка при создании заявки. Пожалуйста, позвоните в УК."
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
                await update.message.reply_text("За многократное использование нецензурной лексики диалог будет прекращен.")
                return
            else:
                await update.message.reply_text("Пожалуйста, избегайте нецензурной лексики в сообщениях.")
                return

        # Обработка в зависимости от режима
        if state.mode == 'SERVICE_REQUEST':
            await self.handle_service_request(update, context, text)

        elif state.mode == 'ADDRESS_INPUT':
            await self.handle_address_input(update, context, text)

        elif state.mode == 'CONFIRMATION':
            # ИСПРАВЛЕНО: Голосовой интерфейс - обрабатываем текстовые "да"/"нет"
            text_lower = text.lower().strip()

            # Слова подтверждения
            confirmation_words = ['да', 'верно', 'правильно', 'точно', 'так', 'согласен', 'подтверждаю', 'yes', 'y']

            # Слова отрицания
            denial_words = ['нет', 'неправ', 'не та', 'другая', 'не то', 'ошиб', 'неверно', 'no', 'n']

            if any(word in text_lower for word in confirmation_words):
                # Подтверждение - создаем заявку или запрашиваем адрес
                if not state.address_components or not state.address_components.get('street'):
                    state.mode = 'ADDRESS_INPUT'
                    await update.message.reply_text(
                        f"Принято! Услуга: {state.current_service_name}\n\n"
                        "Пожалуйста, укажите адрес:\n"
                        "Улица и номер дома (и квартиры, если нужно)\n\n"
                        "Например: ул. Ленина, д. 5, кв. 10"
                    )
                else:
                    # Все данные есть - создаем заявку
                    await self.finalize_application(update, context)
                    return

            elif any(word in text_lower for word in denial_words):
                # ИСПРАВЛЕНО (2025-12-25): Умный вопрос от AI агента вместо хардкода
                state.mode = 'ADDRESS_CHECK'
                state.current_service_id = None
                state.current_service_name = None
                clarification = await self._ask_ai_clarification(text, state)
                await update.message.reply_text(clarification)
            else:
                # ИСПРАВЛЕНО (2025-12-25): Убрана фраза "опишите проблему другими словами"
                await update.message.reply_text(
                    "Пожалуйста, ответьте да или нет, или уточните что именно случилось."
                )

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

    async def _ask_ai_clarification(self, text: str, state: ServiceBotState) -> str:
        """
        ИСПРАВЛЕНО (2025-12-25): Спрашивает у AI агента как уточнить
        ИСПРАВЛЕНО (2026-01-06): Убрано использование state.last_user_message

        УБРАНО: Хардкод с перечислениями "(кран, труба, батарея)"
        ДОБАВЛЕНО: AI генерация вопросов без перечислений
        """
        # ИСПРАВЛЕНО (2026-01-06): Не используем state.last_user_message - нет такого атрибута
        context = f"Текущее сообщение пользователя: {text}"

        prompt = f"""Ты - опытный диспетчер управляющей компании.

{context}

Задай ОДИН уточняющий вопрос чтобы понять проблему пользователя.

ПРИМЕРЫ:
- "Где именно течет?" (если упоминалась вода/течь)
- "Что именно сломалось?" (если поломка)
- "Откуда запах?" (если запах)

КРИТИЧЕСКИ ВАЖНО:
- НЕ используй перечисления в скобках!
- Вопрос должен быть КОНКРЕТНЫМ
- Верни только вопрос без дополнительных слов

Вопрос:"""

        if not self.message_handler or not self.message_handler.main_agent:
            return "Уточните, пожалуйста: что именно случилось?"

        try:
            response, _ = await self.message_handler.main_agent.ai_agent._call_yandex_gpt(prompt)
            return response.strip()
        except Exception as e:
            logger.error(f"Ошибка AI генерации вопроса: {e}")
            return "Уточните, пожалуйста: что именно сломалось, течет или не работает?"

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик ошибок"""
        logger.error(f"Exception while handling an update: {context.error}")

        # Отправляем сообщение об ошибке пользователю
        if update and hasattr(update, 'message'):
            try:
                await update.message.reply_text(
                    "Произошла ошибка. Пожалуйста, попробуйте позже."
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
    # ИСПРАВЛЕНО: Убран CallbackQueryHandler - голосовой интерфейс без кнопок
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_message))

    # Добавление обработчика ошибок
    application.add_error_handler(bot.error_handler)

    print(f"Улучшенный бот {bot.bot_name} v2.0 запускается с системой обнаружения услуг...")

    # Запуск бота
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()