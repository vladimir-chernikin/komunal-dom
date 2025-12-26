#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Сервис коммуникативных скриптов для AI бота

Назначение:
- Единая система управления фразами бота
- Fallback при недоступности AI
- Заполнение пауз в аудио диалоге
- Уточняющие вопросы и подтверждения

Дата создания: 2025-12-26
ТЗ: #26-12
"""

import logging
from typing import Dict, Optional
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class CommunicativeScriptsService:
    """Сервис коммуникативных скриптов"""

    def __init__(self):
        """Инициализация сервиса"""
        self._cache = {}
        self._cache_timestamp = None
        logger.info("CommunicativeScriptsService инициализирован")

    def get_script(self, context: Dict) -> Optional[str]:
        """
        Получить скрипт по контексту

        Args:
            context: {
                'channel': 'telegram' | 'audio' | 'both',
                'script_type': 'fallback' | 'pause' | 'greeting' | 'clarification' | 'confirmation' | 'error',
                'candidate_count': int,
                'is_followup': bool,
                'dialog_turn': int,
                'error_type': str | None
            }

        Returns:
            str: Текст скрипта или None
        """
        try:
            # Извлекаем параметры контекста
            channel = context.get('channel', 'telegram')
            script_type = context.get('script_type', 'fallback')
            dialog_turn = context.get('dialog_turn', 0)

            logger.info(
                f"CommunicativeScripts: поиск скрипта | "
                f"channel={channel}, type={script_type}, turn={dialog_turn}"
            )

            # Ищем скрипт в БД
            def find_script_sync():
                from message_handler.models import CommunicativeScript

                scripts = CommunicativeScript.objects.filter(
                    is_active=True,
                    script_type=script_type,
                    channel__in=[channel, 'both']
                ).filter(
                    min_dialog_turn__lte=dialog_turn
                ).filter(
                    max_dialog_turn__gte=dialog_turn
                ) | CommunicativeScript.objects.filter(
                    is_active=True,
                    script_type=script_type,
                    channel__in=[channel, 'both'],
                    max_dialog_turn=-1
                ).filter(
                    min_dialog_turn__lte=dialog_turn
                )

                # Сортируем по приоритету
                scripts = scripts.order_by('-priority')

                return list(scripts)

            scripts = sync_to_async(find_script_sync)()

            if not scripts:
                logger.warning(f"Скрипты не найдены: channel={channel}, type={script_type}")
                return None

            # Проверяем условия для каждого скрипта
            for script in scripts:
                if self._check_conditions(script.conditions, context):
                    logger.info(
                        f"Скрипт найден: {script.script_name} | "
                        f"text='{script.text[:50]}...'"
                    )
                    return script.text

            logger.warning(f"Подходящий скрипт не найден: channel={channel}, type={script_type}")
            return None

        except Exception as e:
            logger.error(f"Ошибка получения скрипта: {e}")
            return None

    def _check_conditions(self, conditions: Dict, context: Dict) -> bool:
        """
        Проверяет условия triggerа

        Args:
            conditions: JSON условия из БД
            context: Контекст вызова

        Returns:
            bool: True если условия выполнены
        """
        if not conditions:
            return True

        # Проверка candidate_count
        if 'candidate_count' in conditions:
            if context.get('candidate_count', 0) != conditions['candidate_count']:
                return False

        # Проверка is_followup
        if 'is_followup' in conditions:
            if context.get('is_followup', False) != conditions['is_followup']:
                return False

        # Проверка error_type
        if 'error_type' in conditions:
            if context.get('error_type') != conditions['error_type']:
                return False

        return True

    async def get_fallback_message(
        self,
        channel: str = 'telegram',
        candidate_count: int = 0,
        is_followup: bool = False,
        dialog_turn: int = 1
    ) -> str:
        """
        Получить fallback сообщение при ошибке AI

        Args:
            channel: Канал связи
            candidate_count: Количество кандидатов
            is_followup: Это followup вопрос
            dialog_turn: Номер хода диалога

        Returns:
            str: Текст fallback сообщения
        """
        context = {
            'channel': channel,
            'script_type': 'fallback',
            'candidate_count': candidate_count,
            'is_followup': is_followup,
            'dialog_turn': dialog_turn
        }

        message = await self.get_script(context)

        if not message:
            # Fallback на hardcoded сообщения
            if candidate_count == 0 and not is_followup:
                message = "Пожалуйста, уточните где именно это произошло и опишите подробнее, что случилось."
            elif candidate_count == 0 and is_followup:
                message = "Уточните, пожалуйста: что именно сломалось, течет или не работает?"
            else:
                message = "Пожалуйста, опишите проблему другими словами."

        return message

    async def get_pause_message(
        self,
        channel: str = 'audio',
        dialog_turn: int = 1
    ) -> Optional[str]:
        """
        Получить сообщение для заполнения паузы (audio)

        Args:
            channel: Канал связи (обычно 'audio')
            dialog_turn: Номер хода диалога

        Returns:
            str: Текст для паузы или None
        """
        context = {
            'channel': channel,
            'script_type': 'pause',
            'dialog_turn': dialog_turn,
            'is_followup': dialog_turn > 1
        }

        return await self.get_script(context)

    async def get_error_message(
        self,
        error_type: str = 'api_unavailable',
        channel: str = 'telegram'
    ) -> str:
        """
        Получить сообщение об ошибке

        Args:
            error_type: Тип ошибки
            channel: Канал связи

        Returns:
            str: Текст сообщения об ошибке
        """
        context = {
            'channel': channel,
            'script_type': 'error',
            'error_type': error_type,
            'dialog_turn': 1
        }

        message = await self.get_script(context)

        if not message:
            message = "Извините, технические сложности. Попробуйте переформулировать вопрос."

        return message

    def get_clarification_script(
        self,
        candidates: list,
        channel: str = 'telegram'
    ) -> Optional[str]:
        """
        Получить скрипт для уточняющего вопроса

        Args:
            candidates: Список кандидатов услуг
            channel: Канал связи

        Returns:
            str: Текст уточняющего вопроса или None
        """
        # Анализируем кандидатов для выбора скрипта
        if not candidates:
            return None

        # Извлекаем уникальные значения атрибутов
        locations = set()
        categories = set()
        incidents = set()

        for c in candidates:
            if c.get('location_type'):
                locations.add(c['location_type'])
            if c.get('category'):
                categories.add(c['category'])
            if c.get('incident_type'):
                incidents.add(c['incident_type'])

        # Формируем условия для поиска скрипта
        conditions = {}

        if len(locations) >= 2:
            conditions['ambiguous_location'] = True

        if len(categories) >= 2:
            conditions['ambiguous_category'] = True

        if len(incidents) >= 2:
            conditions['ambiguous_incident'] = True

        # Ищем подходящий скрипт
        def find_clarification_sync():
            from message_handler.models import CommunicativeScript

            scripts = CommunicativeScript.objects.filter(
                is_active=True,
                script_type='clarification',
                channel__in=[channel, 'both']
            ).order_by('-priority')

            return list(scripts)

        scripts = sync_to_async(find_clarification_sync)()

        for script in scripts:
            # Проверяем условия
            if self._check_conditions(script.conditions, {'conditions': conditions}):
                return script.text

        return None


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ СКРИПТОВ ПО УМОЛЧАНИЮ
# ============================================================================

def _init_default_scripts():
    """
    Инициализация скриптов по умолчанию в БД

    Вызывается один раз при первом запуске
    """
    from message_handler.models import CommunicativeScript

    default_scripts = [
        {
            'script_name': 'fallback_no_candidates',
            'script_type': 'fallback',
            'channel': 'telegram',
            'text': 'Пожалуйста, уточните где именно это произошло и опишите подробнее, что случилось.',
            'conditions': {'candidate_count': 0, 'is_followup': False},
            'priority': 1.0,
            'min_dialog_turn': 1,
            'max_dialog_turn': 3,
            'category': 'general',
            'notes': 'Fallback когда нет кандидатов (первый вопрос)'
        },
        {
            'script_name': 'fallback_followup_clarify',
            'script_type': 'fallback',
            'channel': 'telegram',
            'text': 'Уточните, пожалуйста: что именно сломалось, течет или не работает?',
            'conditions': {'candidate_count': 0, 'is_followup': True},
            'priority': 1.0,
            'min_dialog_turn': 2,
            'max_dialog_turn': -1,
            'category': 'followup',
            'notes': 'Fallback когда нет кандидатов (followup)'
        },
        {
            'script_name': 'pause_thinking',
            'script_type': 'pause',
            'channel': 'audio',
            'text': 'Хороший вопрос, уточню...',
            'conditions': {'is_followup': True},
            'priority': 1.0,
            'min_dialog_turn': 2,
            'max_dialog_turn': -1,
            'category': 'thinking',
            'notes': 'Пауза когда AI думает (аудио режим)'
        },
        {
            'script_name': 'error_api_unavailable',
            'script_type': 'error',
            'channel': 'both',
            'text': 'Извините, технические сложности. Попробуйте переформулировать вопрос.',
            'conditions': {'error_type': 'api_unavailable'},
            'priority': 1.0,
            'min_dialog_turn': 0,
            'max_dialog_turn': -1,
            'category': 'technical',
            'notes': 'Ошибка когда API недоступен'
        },
        {
            'script_name': 'greeting_audio',
            'script_type': 'greeting',
            'channel': 'audio',
            'text': 'Здравствуйте! Управляющая компания Аспект. Чем могу помочь?',
            'conditions': {},
            'priority': 1.0,
            'min_dialog_turn': 1,
            'max_dialog_turn': 1,
            'category': 'greeting',
            'notes': 'Приветствие для аудио режима'
        }
    ]

    created_count = 0

    for script_data in default_scripts:
        script_name = script_data['script_name']

        # Проверяем существует ли скрипт
        if CommunicativeScript.objects.filter(script_name=script_name).exists():
            logger.info(f"Скрипт '{script_name}' уже существует, пропускаем")
            continue

        # Создаем скрипт
        CommunicativeScript.objects.create(**script_data)
        created_count += 1
        logger.info(f"Создан скрипт: {script_name}")

    logger.info(f"Инициализация скриптов завершена: создано {created_count} скриптов")
    return created_count


if __name__ == '__main__':
    # Тестирование
    import asyncio

    async def test():
        service = CommunicativeScriptsService()

        # Тест fallback
        msg = await service.get_fallback_message(
            channel='telegram',
            candidate_count=0,
            is_followup=False,
            dialog_turn=1
        )
        print(f"Fallback: {msg}")

        # Тест pause
        msg = await service.get_pause_message(channel='audio', dialog_turn=2)
        print(f"Pause: {msg}")

        # Тест error
        msg = await service.get_error_message(error_type='api_unavailable')
        print(f"Error: {msg}")

    asyncio.run(test())
