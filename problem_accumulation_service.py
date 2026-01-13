"""
ProblemAccumulationService - Микросервис для итеративного накопления описания проблемы

Принцип работы:
- 'привет' → txtPrb = '' (нет значимой информации)
- 'у меня течет' → txtPrb = 'у пользователя течет'
- 'Где течет?' - 'В зале' → txtPrb = 'у пользователя течет в зале'
- 'Что именно течет' - 'Батарея' → txtPrb = 'у пользователя течет в зале из батареи'

ИСПРАВЛЕНО (2026-01-13):
- Добавлен детектор отказа пользователя
- При отказе добавляется пометка в txtPrb: "пользователь не уверен что это услуга XXX"

Автор: Claude Sonnet
Дата: 2025-12-26
"""

import logging
import json
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class ProblemAccumulationService:
    """
    Микросервис для итеративного накопления описания проблемы.

    Предназначен для работы в аудио-диалогах где пользователь говорит короткими фразами,
    которые нужно накапливать в единое описание проблемы.
    """

    def __init__(self, ai_agent_service):
        """
        Args:
            ai_agent_service: Экземпляр AIAgentService для вызова LLM
        """
        self.ai_agent = ai_agent_service

    async def extract_and_accumulate(
        self,
        message_text: str,
        current_problem: str,
        bot_question: str = None,
        dialog_history: List[Dict] = None,
        session_id: str = None,
        message_id: int = None
    ) -> Dict[str, Any]:
        """
        Извлекает информацию из сообщения и накапливает описание проблемы.

        Args:
            message_text: Текущее сообщение пользователя
            current_problem: Текущее описание проблемы (txtPrb)
            bot_question: Последний вопрос бота (для понимания контекста)
            dialog_history: История диалога
            session_id: ID сессии (для логирования LLM)
            message_id: ID сообщения (для логирования LLM)

        Returns:
            {
                'updated_problem': str,  # Обновленное txtPrb
                'extracted_info': dict,  # Извлеченная информация
                'is_meaningful': bool,   # Содержит ли сообщение полезную информацию
                'is_refusal': bool,      # ИСПРАВЛЕНО (2026-01-13): Является ли сообщением отказом
                'new_info': str,         # Краткое описание новой информации
                'fields': {              # Извлеченные поля
                    'problem': str | None,
                    'location': str | None,
                    'source': str | None,
                    'category': str | None,
                    'severity': str | None,
                    'intensity': str | None,
                    'object': str | None
                }
            }
        """
        # ИСПРАВЛЕНО (2026-01-13): Детектор отказа пользователя
        if self._is_refusal(message_text):
            logger.warning(f"[REFUSAL] Обнаружен отказ пользователя: '{message_text[:80]}'")

            # Извлекаем название услуги из последнего вопроса бота
            refused_service = self._extract_service_from_question(bot_question)

            # Формируем обновленное txtPrb с пометкой об отказе
            if current_problem:
                updated_problem = f"{current_problem}. Пользователь не уверен что это услуга '{refused_service}'"
            else:
                updated_problem = f"Пользователь не уверен что это услуга '{refused_service}'"

            return {
                'updated_problem': updated_problem,
                'extracted_info': {},
                'is_meaningful': False,
                'is_refusal': True,  # ИСПРАВЛЕНО (2026-01-13): Флаг отказа
                'new_info': f"Пользователь отказался от услуги '{refused_service}'",
                'fields': {}
            }

        # ИСПРАВЛЕНО (2025-12-28): Отладочные логи входящих параметров
        logger.info("[SEARCH] ProblemAccumulationService ВХОДЯЩИЕ ПАРАМЕТРЫ:")
        logger.info(f"  [NOTE] message_text: '{message_text[:80]}'")
        logger.info(f"  [NOTE] current_problem: '{current_problem[:80] if current_problem else '(пусто)'}'")
        logger.info(f"  ❓ bot_question: '{bot_question[:80] if bot_question else '(нет)'}'")
        logger.info(f"  [LIST] dialog_history: {len(dialog_history) if dialog_history else 0} сообщений")

        # Формируем промпт для LLM
        prompt = self._create_accumulation_prompt(
            message_text, current_problem, bot_question, dialog_history
        )

        # ИСПРАВЛЕНО (2025-12-28): Логируем промт
        logger.info(f"🤖 ProblemAccumulation PROMPT:")
        logger.info(f"{'=' * 80}")
        logger.info(f"{prompt[:500]}...")
        logger.info(f"{'=' * 80} (длина: {len(prompt)} символов)")

        try:
            # Вызываем LLM через публичный метод call_llm
            # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id для логирования
            response_text, usage = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite',
                session_id=session_id,  # ИСПРАВЛЕНО (2026-01-06)
                message_id=message_id   # ИСПРАВЛЕНО (2026-01-06)
            )

            # ИСПРАВЛЕНО (2025-12-28): Логируем ответ
            logger.info(f"🤖 ProblemAccumulation ОТВЕТ LLM:")
            logger.info(f"  [NOTE] Raw response: '{response_text[:200]}'")
            logger.info(f"  💰 Usage: {usage}")

            # Пытаемся распарсить JSON
            result = self._parse_llm_response(response_text, current_problem)

            # ИСПРАВЛЕНО (2026-01-05): КРИТИЧЕСКИ ВАЖНО - если is_meaningful=false, сохраняем current_problem!
            if not result['is_meaningful']:
                result['updated_problem'] = current_problem
                logger.info(f"⚠️ is_meaningful=False → сохраняем текущий txtPrb БЕЗ ИЗМЕНЕНИЙ")

            # ИСПРАВЛЕНО (2025-12-28): Детальный лог результата
            logger.info(f"[OK] ProblemAccumulation РЕЗУЛЬТАТ:")
            logger.info(f"  [SEARCH] is_meaningful: {result['is_meaningful']}")
            logger.info(f"  [NOTE] new_info: '{result['new_info']}'")
            logger.info(f"  [NOTE] updated_problem: '{result['updated_problem']}'")
            logger.info(f"  🔧 fields: {json.dumps(result['fields'], ensure_ascii=False)}")

            logger.info(
                f"ProblemAccumulation: '{message_text[:50]}...' → "
                f"is_meaningful={result['is_meaningful']}, "
                f"updated_problem='{result['updated_problem'][:80]}...'"
            )

            return result

        except Exception as e:
            logger.error(f"Ошибка в ProblemAccumulationService: {e}")
            # В случае ошибки возвращаем текущее состояние без изменений
            return {
                'updated_problem': current_problem,
                'extracted_info': {},
                'is_meaningful': False,
                'new_info': '',
                'fields': {
                    'problem': None,
                    'location': None,
                    'source': None,
                    'category': None,
                    'severity': None,
                    'intensity': None,
                    'object': None
                }
            }

    def _create_accumulation_prompt(
        self,
        message_text: str,
        current_problem: str,
        bot_question: str = None,
        dialog_history: List[Dict] = None
    ) -> str:
        """Создает промпт для LLM."""

        # Контекст истории диалога (последние 3 сообщения)
        history_context = ""
        if dialog_history and len(dialog_history) > 1:
            recent_messages = dialog_history[-4:]
            history_context = "\nПОСЛЕДНИЕ СООБЩЕНИЯ (для контекста):\n"
            for msg in recent_messages:
                role = msg.get('role', 'unknown')
                text = msg.get('text', '')[:100]
                history_context += f"  {role}: {text}\n"

        prompt = f"""Ты - аналитик, извлекающий и накапливающий факты из диалога.

ТЕКУЩЕЕ ОПИСАНИЕ ПРОБЛЕМЫ:
{current_problem if current_problem else '(пусто - начало диалога)'}

ПРЕДЫДУЩИЙ ВОПРОС БОТА (на который пользователь отвечает):
{bot_question if bot_question else '(первое сообщение в диалоге)'}

ТЕКУЩЕЕ СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ:
{message_text}
{history_context}

ЗАДАЧА:
1. Определи содержит ли сообщение ПОЛЕЗНУЮ информацию о проблеме
2. Извлеки конкретные факты из сообщения
3. Обнови описание проблемы, добавив новую информацию

ВАЖНО:
- Если "привет", "да", "нет", "ок", "спасибо", "пожалуйста" → is_meaningful=false
- ⛔ КРИТИЧЕСКИ ВАЖНО: Если bot_question содержит вопрос ("Где", "Что", "Какой"), то ответ ВСЕГДА is_meaningful=true!
  Даже если ответ короткий ("в зале", "труба", "батарея") - это ЗНАЧИМЫЙ ответ на вопрос бота!
- Объединяй информацию с current_problem (НЕ копируй, а ДОБАВЛЯЙ)
- НЕ повторяй уже известную информацию
- Извлекай МАКСИМУМ конкретики: локация, источник, категория, серьезность
- txtPrb должно быть КРАТКИМ и ПОНЯТНЫМ (1-2 предложения)
- ⛔ КРИТИЧЕСКИ ВАЖНО: Если is_meaningful=false, ТОЧНО скопируй current_problem в updated_problem БЕЗ ИЗМЕНЕНИЙ!

Верни ТОЛЬКО JSON (без markdown):

{{
    "is_meaningful": true или false,
    "new_info": "краткое описание НОВОЙ информации (5-10 слов)",
    "updated_problem": "полное обновленное описание проблемы (1-2 предложения)",
    "fields": {{
        "problem": "проблема (течет, сломался, запах, шум и т.д.)",
        "location": "локация (зал, ванная, кухня, подъезд и т.д.)",
        "source": "источник (труба, батарея, кран, розетка и т.д.)",
        "category": "категория (отопление, водоснабжение, электрика и т.д.)",
        "severity": "серьезность (авария, небольшая проблема)",
        "intensity": "интенсивность (сильно, слабо, постоянно)",
        "object": "объект (если упоминается конкретный объект)"
    }}
}}

ПРИМЕРЫ:

ПРИМЕР 1:
current_problem: "(пусто)"
bot_question: "(не было)"
message_text: "у меня течет"
Ответ:
{{
    "is_meaningful": true,
    "new_info": "у пользователя течет",
    "updated_problem": "у пользователя течет",
    "fields": {{
        "problem": "течет",
        "location": null,
        "source": null,
        "category": null,
        "severity": null,
        "intensity": null,
        "object": null
    }}
}}

ПРИМЕР 1.5 (ОТВЕТ НА ВОПРОС БОТА - ВСЕГДА ЗНАЧИМЫЙ!):
current_problem: "у пользователя прорвало трубу"
bot_question: "Где именно?"
message_text: "в квартире"
Ответ:
{{
    "is_meaningful": true,
    "new_info": "локация: квартира",
    "updated_problem": "у пользователя прорвало трубу в квартире",
    "fields": {{
        "problem": "прорвало",
        "location": "квартира",
        "source": "труба",
        "category": null,
        "severity": null,
        "intensity": null,
        "object": "труба"
    }}
}}

ПРИМЕР 1.6 (КРИТИЧЕСКИ ВАЖНО - ОБЪЕДИНЯЙ, А НЕ ЗАМЕНЯЙ!):
current_problem: "у пользователя прорыв трубы в квартире"
bot_question: "Что именно сломалось?"
message_text: "кран"
❌ НЕПРАВИЛЬНЫЙ ОТВЕТ:
{{
    "updated_problem": "кран"  ❌❌❌ ЭТО НЕВЕРНО! Ты ЗАМЕНИЛ всю проблему!
}}
✅ ПРАВИЛЬНЫЙ ОТВЕТ:
{{
    "is_meaningful": true,
    "new_info": "объект: кран",
    "updated_problem": "у пользователя прорыв трубы в квартире, сломался кран",
    "fields": {{
        "problem": "прорыв",
        "location": "квартира",
        "source": "труба",
        "category": null,
        "object": "кран"
    }}
}}

ПРИМЕР 2:
current_problem: "у пользователя течет"
bot_question: "Где именно?"
message_text: "В зале"
Ответ:
{{
    "is_meaningful": true,
    "new_info": "локация: зал",
    "updated_problem": "у пользователя течет в зале",
    "fields": {{
        "problem": "течет",
        "location": "зал",
        "source": null,
        "category": null,
        "severity": null,
        "intensity": null,
        "object": null
    }}
}}

ПРИМЕР 3:
current_problem: "у пользователя течет в зале"
bot_question: "Что именно течет?"
message_text: "Батарея"
Ответ:
{{
    "is_meaningful": true,
    "new_info": "источник: батарея (отопление)",
    "updated_problem": "у пользователя течет из батареи (отопление) в зале",
    "fields": {{
        "problem": "течет",
        "location": "зал",
        "source": "батарея",
        "category": "отопление",
        "severity": null,
        "intensity": null,
        "object": "батарея"
    }}
}}

ПРИМЕР 4 (НЕЗНАЧИМЫЕ СООБЩЕНИЯ):
current_problem: "у пользователя течет из батареи в зале"
bot_question: "Какой напор?"
message_text: "постоянно"
Ответ:
{{
    "is_meaningful": false,
    "new_info": "интенсивность: постоянно",
    "updated_problem": "у пользователя течет из батареи в зале постоянно",
    "fields": {{
        "problem": "течет",
        "location": "зал",
        "source": "батарея",
        "category": "отопление",
        "severity": null,
        "intensity": "постоянно",
        "object": "батарея"
    }}
}}

ПРИМЕР 5 (НЕЗНАЧИМЫЕ СООБЩЕНИЯ):
current_problem: "у пользователя течет"
bot_question: null
message_text: "Привет!"
Ответ:
{{
    "is_meaningful": false,
    "new_info": "",
    "updated_problem": "у пользователя течет",
    "fields": {{
        "problem": "течет",
        "location": null,
        "source": null,
        "category": null,
        "severity": null,
        "intensity": null,
        "object": null
    }}
}}

ПРИМЕР 6 (НЕЗНАЧИМЫЕ СООБЩЕНИЯ - сохранение контекста):
current_problem: "у пользователя течет из трубы у батареи в зале"
bot_question: "Какой характер у течи?"
message_text: "а зачем тебе это?"
Ответ:
{{
    "is_meaningful": false,
    "new_info": "",
    "updated_problem": "у пользователя течет из трубы у батареи в зале",
    "fields": {{
        "problem": "течет",
        "location": "зал",
        "source": "труба у батареи",
        "category": null,
        "severity": null,
        "intensity": null,
        "object": "труба"
    }}
}}

ВАЖНО ПРИМЕЧАНИЕ: В примере 6 updated_problem ТОЧНО совпадает с current_problem!

JSON:"""

        return prompt

    def _parse_llm_response(self, response_text: str, current_problem: str) -> Dict[str, Any]:
        """Парсит ответ LLM и возвращает структурированный результат."""
        try:
            # Убираем markdown если есть
            response_text = response_text.strip()
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.split('```')[0]

            # Парсим JSON
            result = json.loads(response_text.strip())

            # Валидация полей
            return {
                'updated_problem': result.get('updated_problem', current_problem),
                'extracted_info': {},
                'is_meaningful': result.get('is_meaningful', False),
                'new_info': result.get('new_info', ''),
                'fields': {
                    'problem': result.get('fields', {}).get('problem'),
                    'location': result.get('fields', {}).get('location'),
                    'source': result.get('fields', {}).get('source'),
                    'category': result.get('fields', {}).get('category'),
                    'severity': result.get('fields', {}).get('severity'),
                    'intensity': result.get('fields', {}).get('intensity'),
                    'object': result.get('fields', {}).get('object')
                }
            }

        except json.JSONDecodeError as e:
            logger.error(f"Не удалось распарсить JSON из LLM ответа: {e}")
            logger.debug(f"Ответ LLM: {response_text[:500]}")
            # Возвращаем текущее состояние без изменений
            return {
                'updated_problem': current_problem,
                'extracted_info': {},
                'is_meaningful': False,
                'new_info': '',
                'fields': {
                    'problem': None,
                    'location': None,
                    'source': None,
                    'category': None,
                    'severity': None,
                    'intensity': None,
                    'object': None
                }
            }

    def get_txtPrb_from_metadata(self, dialog_history: List[Dict]) -> str:
        """
        Извлекает txtPrb из metadata последнего сообщения в истории.

        Args:
            dialog_history: История диалога

        Returns:
            str: Текущее значение txtPrb или пустая строка
        """
        if not dialog_history:
            return ""

        # Ищем последнее сообщение с metadata
        for msg in reversed(dialog_history[-5:]):  # Последние 5 сообщений
            metadata = msg.get('metadata', {})
            if isinstance(metadata, dict) and 'txtPrb' in metadata:
                return metadata['txtPrb']

        return ""

    def _is_refusal(self, text: str) -> bool:
        """
        ИСПРАВЛЕНО (2026-01-13): Проверяет является ли текст отказом пользователя

        Args:
            text: Текст сообщения пользователя

        Returns:
            True если текст содержит отказ, иначе False
        """
        if not text:
            return False

        refusal_keywords = [
            'нет', 'не то', 'не правильно', 'неправильно',
            'ошибаешься', 'ошиблись', 'неверно',
            'не это', 'не подходит', 'не тот',
            'не та', 'не такие'
        ]

        text_lower = text.lower().strip()

        # Проверяем наличие ключевых слов
        for keyword in refusal_keywords:
            if keyword in text_lower:
                return True

        return False

    def _extract_service_from_question(self, bot_question: str) -> str:
        """
        ИСПРАВЛЕНО (2026-01-13): Извлекает название услуги из вопроса бота

        Args:
            bot_question: Последний вопрос бота

        Returns:
            Название услуги или 'предложенная услуга' если не удалось извлечь
        """
        if not bot_question:
            return 'предложенная услуга'

        # Ищем паттерны типа "Похоже на XXX" или "у вас: XXX"
        import re

        # Паттерн 1: "Похоже на [услуга]"
        pattern1 = r'похоже на\s+([^,.:;!?\n]+)'
        match1 = re.search(pattern1, bot_question, re.IGNORECASE)
        if match1:
            return match1.group(1).strip()

        # Паттерн 2: "у вас: [услуга]" или "Понял, у вас: [услуга]"
        pattern2 = r'у вас:\s*([^,.:;!?\n]+)'
        match2 = re.search(pattern2, bot_question, re.IGNORECASE)
        if match2:
            return match2.group(1).strip()

        # Паттерн 3: "Это [услуга]?"
        pattern3 = r'это\s+([^,.:;!?\n]+)\?'
        match3 = re.search(pattern3, bot_question, re.IGNORECASE)
        if match3:
            return match3.group(1).strip()

        # Если не удалось извлечь - возвращаем общую фразу
        return 'предложенная услуга'

    def calculate_filter_confidence(self, txtPrb: str, fields: Dict) -> Dict[str, Dict]:
        """
        Рассчитывает уверенность (confidence) для фильтров на основе txtPrb.

        Правила:
        - Если поле явно упомянуто в txtPrb и подтверждено fields → confidence 0.95
        - Если поле есть в fields но НЕ в txtPrb → confidence 0.70
        - Если поле НЕ определено → confidence 0.0

        Args:
            txtPrb: Накопленное описание проблемы
            fields: Извлеченные поля {'location': 'зал', 'category': 'отопление', ...}

        Returns:
            {
                'location_type': {'value': 'Индивидуальное', 'confidence': 0.95},
                'category': {'value': 'отопление', 'confidence': 0.95},
                'incident_type': {'value': 'Инцидент', 'confidence': 0.85}
            }
        """
        filters = {}

        # Определяем incident_type по ключевым словам
        # ИСПРАВЛЕНО (2026-01-06): Переименовано incident -> incident_type для единообразия
        # ИСПРАВЛЕНО (2026-01-13): Добавлены 'капает', 'льет' как ключевые слова инцидентов
        txtPrb_lower = txtPrb.lower()
        if any(word in txtPrb_lower for word in ['авария', 'прорв', 'течет', 'затоп', 'сломал', 'не работает', 'капает', 'льет', 'мокр']):
            incident_value = 'Инцидент'
            incident_confidence = 0.90
        else:
            incident_value = 'Запрос'
            incident_confidence = 0.70

        filters['incident_type'] = {'value': incident_value, 'confidence': incident_confidence}

        # Определяем location_type
        # ИСПРАВЛЕНО (2026-01-06): Переименовано location -> location_type для единообразия
        location = fields.get('location')
        if location:
            # Проверяем упомянута ли локация в txtPrb
            if location.lower() in txtPrb_lower:
                filters['location_type'] = {'value': 'Индивидуальное' if self._is_indoor_location(location) else 'Общедомовое', 'confidence': 0.95}
            else:
                filters['location_type'] = {'value': 'Индивидуальное', 'confidence': 0.70}

        # Определяем category
        category = fields.get('category')
        if category:
            if category.lower() in txtPrb_lower or any(word in txtPrb_lower for word in [category.lower()]):
                filters['category'] = {'value': category, 'confidence': 0.95}
            else:
                filters['category'] = {'value': category, 'confidence': 0.70}

        # Определяем object_description
        obj = fields.get('object') or fields.get('source')
        if obj:
            filters['object_description'] = {'value': obj, 'confidence': 0.95}

        return filters

    def _is_indoor_location(self, location: str) -> bool:
        """Определяет является ли локация индивидуальной (в квартире)."""
        indoor_keywords = ['ванной', 'кухн', 'зал', 'спальн', 'коридор', 'туалет', 'комнат']
        return any(keyword in location.lower() for keyword in indoor_keywords)
