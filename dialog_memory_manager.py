#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DialogMemoryManager - менеджер памяти диалогов для Telegram бота УК "Аспект"

Этот модуль отвечает за:
- Хранение имени пользователя
- Накопление компонентов адреса из разных сообщений
- Историю диалога
- Контекст услуг
- Интеграцию с PostgreSQL для сохранения состояния
"""

import logging
import re
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from django.db import connection

logger = logging.getLogger(__name__)


class DialogMemoryManager:
    """
    Менеджер памяти диалога для накопления информации из сообщений пользователя.

    Основная задача - собирать адрес из кусков в разных сообщениях:
    - Сообщение 1: "ул. Ленина" → запоминает улицу
    - Сообщение 2: "дом 5" → добавляет дом, НЕ ЗАБЫВАЯ улицу
    - Сообщение 3: "кв. 12" → добавляет квартиру, сохраняя всё остальное

    Attributes:
        dialog_id: Уникальный идентификатор диалога (UUID)
        user_id: ID пользователя Telegram
        user_name: Извлеченное имя пользователя
        conversation_history: Полная история сообщений
        extracted_entities: Накопленные компоненты адреса
        current_service_context: Текущая определенная услуга
        previous_services: История услуг в диалоге
        created_at: Время создания диалога
    """

    def __init__(self, dialog_id: str, user_id: int):
        """
        Инициализация менеджера памяти диалога.

        Args:
            dialog_id: Уникальный ID диалога (UUID)
            user_id: Telegram user ID
        """
        self.dialog_id = dialog_id
        self.user_id = user_id
        self.user_name: Optional[str] = None
        self.conversation_history: List[Dict[str, Any]] = []
        self.extracted_entities = {
            'street': None,
            'house_number': None,
            'apartment_number': None,
            'entrance': None
        }
        self.current_service_context: Optional[Dict] = None
        self.previous_services: List[Dict] = []
        self.created_at = datetime.now(timezone.utc)

        logger.info(f"Created DialogMemoryManager for dialog_id={dialog_id}, user_id={user_id}")

    def extract_user_name(self, text: str) -> Optional[str]:
        """
        Извлечь имя пользователя из его сообщения.

        Использует regex паттерны для поиска конструкций:
        - "я Владимир" → "Владимир"
        - "меня зовут Елена" → "Елена"
        - "это Иван" → "Иван"
        - "зовут Петров" → "Петров"

        Args:
            text: Текст сообщения пользователя

        Returns:
            str: Извлеченное имя с капитализированной первой буквой
            None: Если имя не найдено

        Examples:
            >>> memory = DialogMemoryManager("test", 123)
            >>> memory.extract_user_name("Привет, я Владимир")
            'Владимир'

            >>> memory.extract_user_name("Меня зовут Елена Петрова")
            'Елена'

            >>> memory.extract_user_name("Просто вопрос")
            None
        """
        try:
            # Приводим к нижнему регистру для поиска, но сохраним оригинал для извлечения
            text_lower = text.lower()

            # Паттерны для извлечения имени
            patterns = [
                # "меня зовут Елена", "имя Елена Петровна"
                r'(?:меня\s+зовут|имя\s+моё|имя\s+)\s+([а-яёё]+)(?:\s+[а-яёё]+)?',
                # "я Владимир", "я - Владимир", "это Иван"
                r'(?:я\s+(?:это\s+)?|я\s+-)\s*([а-яёё]+)(?:\s+[а-яёё]+)?',
                # "зовут Петр", "зовут Александр", "это Андрей"
                r'(?:зовут\s+|это\s+)([а-яёё]+)(?:\s+[а-яёё]+)?',
                # "Владимир это я" (обратный порядок)
                r'([а-яёё]+(?:\s+[а-яёё]+)?)\s+(?:это\s+)?я\s*',
                # "Я, Владимир," (с запятыми)
                r'я\s*[,\.]\s*([а-яёё]+)(?:\s+[а-яёё]+)?',
            ]

            for pattern in patterns:
                match = re.search(pattern, text_lower)
                if match:
                    name = match.group(1).strip()
                    # Капитализируем первую букву
                    if name:
                        name = name.capitalize()
                        self.user_name = name
                        logger.info(f"Extracted user name: {name} from: '{text[:50]}...'")
                        return name

            logger.debug(f"No user name found in text: '{text[:50]}...'")
            return None

        except Exception as e:
            logger.error(f"Error extracting user name from text '{text}': {e}")
            return None

    def accumulate_address_fragments(self, new_components: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
        """
        КЛЮЧЕВОЙ МЕТОД! Накапливать компоненты адреса из разных сообщений.

        Этот метод обеспечивает "память" бота - он НЕ ЗАБЫВАЕТ предыдущие компоненты адреса.

        Args:
            new_components: Новые компоненты из текущего сообщения
                {
                    'street': 'Ленина',           # опционально
                    'house_number': '5',          # опционально
                    'apartment_number': '12',     # опционально
                    'entrance': '2'               # опционально
                }

        Returns:
            Dict: Текущее состояние всех компонентов адреса

        Examples:
            >>> memory = DialogMemoryManager("test", 123)

            # Сообщение 1: "улица Ленина"
            >>> memory.accumulate_address_fragments({'street': 'Ленина'})
            {'street': 'Ленина', 'house_number': None, 'apartment_number': None, 'entrance': None}

            # Сообщение 2: "дом 5"
            >>> memory.accumulate_address_fragments({'house_number': '5'})
            {'street': 'Ленина', 'house_number': '5', 'apartment_number': None, 'entrance': None}
            # ❗ ВАЖНО: УЛИЦА НЕ ЗАБЫЛАСЬ!

            # Сообщение 3: "квартира 12"
            >>> memory.accumulate_address_fragments({'apartment_number': '12'})
            {'street': 'Ленина', 'house_number': '5', 'apartment_number': '12', 'entrance': None}
        """
        try:
            updated_fields = []

            # Проходим по всем возможным компонентам адреса
            for key in ['street', 'house_number', 'apartment_number', 'entrance']:
                new_value = new_components.get(key)

                # Если новое значение не None и отличается от текущего
                if new_value is not None and new_value != self.extracted_entities.get(key):
                    old_value = self.extracted_entities.get(key)
                    self.extracted_entities[key] = new_value
                    updated_fields.append(f"{key}: {old_value} → {new_value}")
                    logger.info(f"Updated address component {key}: {old_value} → {new_value}")

            if updated_fields:
                logger.info(f"Address fragments accumulated. Updated: {', '.join(updated_fields)}")
            else:
                logger.debug("No new address components to accumulate")

            return self.extracted_entities.copy()

        except Exception as e:
            logger.error(f"Error accumulating address fragments: {e}")
            return self.extracted_entities.copy()

    def get_complete_context(self) -> Dict[str, Any]:
        """
        Получить полный контекст для передачи в другие микросервисы.

        Returns:
            Dict: Полный контекст диалога
                {
                    'dialog_id': UUID,
                    'user_id': int,
                    'user_name': str или None,
                    'extracted_entities': {
                        'street': str или None,
                        'house_number': str или None,
                        'apartment_number': str или None,
                        'entrance': str или None
                    },
                    'history_length': int,
                    'last_messages': List[Dict],  # 3 последних сообщения
                    'current_service': Dict или None,
                    'created_at': ISO string
                }

        Examples:
            >>> memory = DialogMemoryManager("test", 123)
            >>> memory.add_message('user', 'Привет')
            >>> memory.add_message('bot', 'Здравствуйте!')
            >>> context = memory.get_complete_context()
            >>> context['user_id']
            123
            >>> context['history_length']
            2
        """
        try:
            # Получаем последние 3 сообщения
            last_messages = self.conversation_history[-3:] if self.conversation_history else []

            context = {
                'dialog_id': self.dialog_id,
                'user_id': self.user_id,
                'user_name': self.user_name,
                'extracted_entities': self.extracted_entities.copy(),
                'history_length': len(self.conversation_history),
                'last_messages': last_messages,
                'current_service': self.current_service_context,
                'created_at': self.created_at.isoformat(),
                'previous_services_count': len(self.previous_services),
                'dialog_duration_minutes': int((datetime.now(timezone.utc) - self.created_at).total_seconds() / 60)
            }

            logger.debug(f"Generated complete context for dialog {self.dialog_id}")
            return context

        except Exception as e:
            logger.error(f"Error getting complete context: {e}")
            return {
                'dialog_id': self.dialog_id,
                'user_id': self.user_id,
                'error': str(e)
            }

    def add_message(self, role: str, text: str) -> None:
        """
        Добавить сообщение в историю диалога.

        Args:
            role: 'user' или 'bot'
            text: Текст сообщения

        Examples:
            >>> memory = DialogMemoryManager("test", 123)
            >>> memory.add_message('user', "Привет")
            >>> memory.add_message('bot', "Здравствуйте!")
            >>> len(memory.conversation_history)
            2
        """
        try:
            message = {
                'role': role,
                'text': text,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            self.conversation_history.append(message)
            logger.debug(f"Added {role} message to dialog {self.dialog_id}: {text[:50]}...")

        except Exception as e:
            logger.error(f"Error adding message to history: {e}")

    def get_last_user_messages(self, count: int = 5) -> List[str]:
        """
        Получить последние N сообщений пользователя.

        Args:
            count: Количество сообщений для возврата (по умолчанию 5)

        Returns:
            List[str]: Список текстов последних сообщений от пользователя

        Examples:
            >>> memory = DialogMemoryManager("test", 123)
            >>> memory.add_message('user', 'Первое')
            >>> memory.add_message('bot', 'Ответ')
            >>> memory.add_message('user', 'Второе')
            >>> memory.get_last_user_messages(2)
            ['Первое', 'Второе']
        """
        try:
            user_messages = [
                msg['text'] for msg in self.conversation_history
                if msg['role'] == 'user'
            ]
            return user_messages[-count:] if user_messages else []

        except Exception as e:
            logger.error(f"Error getting last user messages: {e}")
            return []

    def get_last_message_text(self) -> Optional[str]:
        """
        Получить текст последнего сообщения в диалоге.

        Returns:
            str: Текст последнего сообщения или None если нет сообщений

        Examples:
            >>> memory = DialogMemoryManager("test", 123)
            >>> memory.add_message('user', 'Привет')
            >>> memory.add_message('bot', 'Здравствуйте!')
            >>> memory.get_last_message_text()
            'Здравствуйте!'
        """
        try:
            if not self.conversation_history:
                return None
            return self.conversation_history[-1].get('text')
        except Exception as e:
            logger.error(f"Error getting last message text: {e}")
            return None

    def update_service_context(self, service_id: int, service_name: str,
                             confidence: float, service_code: str = None) -> None:
        """
        Обновить информацию о текущей услуге.

        Args:
            service_id: ID услуги
            service_name: Название услуги
            confidence: Уверенность в определении (0.0-1.0)
            service_code: Код услуги (опционально)
        """
        try:
            # Если есть текущая услуга, сохраняем ее в историю
            if self.current_service_context:
                self.previous_services.append(self.current_service_context.copy())

            # Обновляем текущую услугу
            self.current_service_context = {
                'service_id': service_id,
                'service_name': service_name,
                'service_code': service_code or str(service_id),
                'confidence': confidence,
                'detected_at': datetime.now(timezone.utc).isoformat()
            }

            logger.info(f"Updated service context: {service_name} (confidence: {confidence})")

        except Exception as e:
            logger.error(f"Error updating service context: {e}")

    def get_address_confidence(self) -> float:
        """
        Рассчитать уверенность в полноте адреса.

        Returns:
            float: Уверенность от 0.0 до 1.0
        """
        try:
            components = ['street', 'house_number', 'apartment_number', 'entrance']
            filled = sum(1 for comp in components if self.extracted_entities.get(comp))
            return filled / len(components)
        except:
            return 0.0

    def is_address_complete(self) -> bool:
        """
        Проверить, достаточен ли адрес для создания заявки.

        Returns:
            bool: True если есть улица и дом
        """
        street = self.extracted_entities.get('street')
        house = self.extracted_entities.get('house_number')
        return bool(street and house)

    def get_full_address_string(self) -> str:
        """
        Сформировать полную строку адреса.

        Returns:
            str: Адрес в формате "ул. Улица, д. Номер, кв. Номер"
        """
        try:
            parts = []

            if self.extracted_entities.get('street'):
                parts.append(f"ул. {self.extracted_entities['street']}")

            if self.extracted_entities.get('house_number'):
                parts.append(f"д. {self.extracted_entities['house_number']}")

            if self.extracted_entities.get('apartment_number'):
                parts.append(f"кв. {self.extracted_entities['apartment_number']}")

            if self.extracted_entities.get('entrance'):
                parts.append(f"подъезд {self.extracted_entities['entrance']}")

            return ", ".join(parts) if parts else "Адрес не указан"

        except Exception as e:
            logger.error(f"Error formatting address string: {e}")
            return "Ошибка адреса"

    def save_to_database(self) -> bool:
        """
        Сохранить состояние диалога в PostgreSQL.

        Returns:
            bool: True если успешно сохранено
        """
        try:
            with connection.cursor() as cursor:
                # Вставляем или обновляем запись в dialog_memory_store
                cursor.execute("""
                    INSERT INTO dialog_memory_store (
                        dialog_id, user_id, user_name,
                        extracted_street, extracted_house_number,
                        extracted_apartment_number, extracted_entrance,
                        context_json, current_service_id, current_service_name,
                        previous_services, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, %s, %s
                    )
                    ON CONFLICT (dialog_id) DO UPDATE SET
                        user_name = EXCLUDED.user_name,
                        extracted_street = EXCLUDED.extracted_street,
                        extracted_house_number = EXCLUDED.extracted_house_number,
                        extracted_apartment_number = EXCLUDED.extracted_apartment_number,
                        extracted_entrance = EXCLUDED.extracted_entrance,
                        context_json = EXCLUDED.context_json,
                        current_service_id = EXCLUDED.current_service_id,
                        current_service_name = EXCLUDED.current_service_name,
                        previous_services = EXCLUDED.previous_services,
                        updated_at = NOW()
                """, [
                    self.dialog_id,
                    self.user_id,
                    self.user_name,
                    self.extracted_entities.get('street'),
                    self.extracted_entities.get('house_number'),
                    self.extracted_entities.get('apartment_number'),
                    self.extracted_entities.get('entrance'),
                    json.dumps(self.get_complete_context(), ensure_ascii=False),
                    self.current_service_context.get('service_id') if self.current_service_context else None,
                    self.current_service_context.get('service_name') if self.current_service_context else None,
                    json.dumps(self.previous_services, ensure_ascii=False),
                    self.created_at,
                    datetime.now(timezone.utc)
                ])

                logger.info(f"Saved dialog memory to database: {self.dialog_id}")
                return True

        except Exception as e:
            logger.error(f"Error saving dialog memory to database: {e}")
            return False

    @classmethod
    def load_from_database(cls, dialog_id: str, user_id: int) -> Optional['DialogMemoryManager']:
        """
        Загрузить состояние диалога из PostgreSQL.

        Args:
            dialog_id: ID диалога
            user_id: ID пользователя

        Returns:
            DialogMemoryManager или None если не найдено
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT * FROM dialog_memory_store WHERE dialog_id = %s AND user_id = %s
                """, [dialog_id, user_id])

                row = cursor.fetchone()
                if not row:
                    return None

                # Создаем экземпляр
                memory = cls(dialog_id, user_id)

                # Восстанавливаем состояние (индексы: 0=id, 1=dialog_id, 2=user_id, 3=user_name, 4=extracted_street, 5=extracted_house_number, 6=extracted_apartment_number, 7=extracted_entrance, 8=context_json, 9=current_service_id, 10=current_service_name, 11=previous_services, 12=created_at, 13=updated_at)
                memory.user_name = row[3]  # user_name (правильный индекс!)
                memory.extracted_entities = {
                    'street': row[4],      # extracted_street (правильный индекс!)
                    'house_number': row[5], # extracted_house_number (правильный индекс!)
                    'apartment_number': row[6], # extracted_apartment_number (правильный индекс!)
                    'entrance': row[7]      # extracted_entrance (правильный индекс!)
                }

                # Загружаем JSON данные
                if row[8]:  # context_json
                    context = json.loads(row[8])
                    memory.conversation_history = context.get('last_messages', [])
                    memory.previous_services = context.get('previous_services', [])

                if row[9] and row[10]:  # current_service_id, current_service_name
                    memory.current_service_context = {
                        'service_id': row[9],
                        'service_name': row[10],
                        'service_code': str(row[9]),
                        'confidence': context.get('current_service', {}).get('confidence', 0.0),
                        'detected_at': context.get('current_service', {}).get('detected_at', '')
                    }

                logger.info(f"Loaded dialog memory from database: {dialog_id}")
                return memory

        except Exception as e:
            logger.error(f"Error loading dialog memory from database: {e}")
            return None