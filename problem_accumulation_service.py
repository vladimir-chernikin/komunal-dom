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
import re
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
                'is_refusal': bool,      # Является ли сообщением отказом
                'refused_service': str,  # Отвергнутая услуга (если is_refusal=True)
                'db_error': bool         # Ошибка загрузки промпта из БД
            }
        """
        # ИСПРАВЛЕНО (2026-01-13): Детектор отказа пользователя
        # ИСПРАВЛЕНО (2026-01-15): При отказе НЕ меняем txtPrb, чтобы не блокировать услугу
        if await self._is_refusal(message_text):
            logger.warning(f"[REFUSAL] Обнаружен отказ пользователя: '{message_text[:80]}'")

            # Извлекаем название услуги от которой отказался пользователь
            refused_service = self._extract_service_from_question(bot_question)

            # ИСПРАВЛЕНО (2026-01-15): НЕ добавляем отказ в txtPrb!
            # Причины:
            # 1. Не блокируем возможность вернуться к этой услуге
            # 2. txtPrb остается чистым описанием проблемы
            # 3. MainAgent сам обрабатывает is_refusal=True и задает уточняющий вопрос
            logger.info(f"[REFUSAL] Отказ от услуги: '{refused_service}', txtPrb сохранен без изменений")

            return {
                'updated_problem': current_problem,  # НЕ меняем txtPrb!
                'extracted_info': {},
                'is_meaningful': False,  # Отказ не содержит новой информации о проблеме
                'is_refusal': True,
                'new_info': f"пользователь отказался от услуги '{refused_service}'",
                'db_error': False,  # ИСПРАВЛЕНО (2026-02-05)
                'refused_service': refused_service
            }

        # Формируем промпт для LLM
        # ИСПРАВЛЕНО (2026-02-05): Добавлен await (функция теперь async)
        prompt = await self._create_accumulation_prompt(
            message_text, current_problem, bot_question, dialog_history
        )

        # ИСПРАВЛЕНО (2026-02-05): Проверяем на fallback-промпт (ошибка БД)
        db_error = 'ТЕХНИЧЕСКАЯ ОШИБКА' in prompt
        if db_error:
            logger.error("[DB_ERROR] Используется fallback-промпт - ошибка загрузки из БД!")

        # ИСПРАВЛЕНО (2025-12-28): Логируем промт
        logger.info(f"🤖 ProblemAccumulation PROMPT:")
        logger.info(f"{'=' * 80}")
        logger.info(f"{prompt[:500]}...")
        logger.info(f"{'=' * 80} (длина: {len(prompt)} символов)")

        try:
            # Вызываем LLM через публичный метод call_llm
            # ИСПРАВЛЕНО (2026-01-06): Передаем session_id и message_id для логирования
            # ИСПРАВЛЕНО (2026-02-24): Передаем service_name для отслеживания микросервиса
            response_text, usage = await self.ai_agent.call_llm(
                prompt=prompt,
                provider=None,  # Используем провайдер из env (DEFAULT_LLM_PROVIDER)
                model=None,  # Используем модель по умолчанию из .env
                session_id=session_id,  # ИСПРАВЛЕНО (2026-01-06)
                message_id=message_id,  # ИСПРАВЛЕНО (2026-01-06)
                caller_service='ProblemAccumulationService',
                prompt_slug=None if db_error else 'problem-accumulation-service',
                prompt_source='python_fallback' if db_error else 'llm_tester'
            )

            # ИСПРАВЛЕНО (2025-12-28): Логируем ответ
            logger.info(f"🤖 ProblemAccumulation ОТВЕТ LLM:")
            logger.info(f"  [NOTE] Raw response: '{response_text[:200]}'")
            logger.info(f"  💰 Usage: {usage}")

            # Пытаемся распарсить JSON
            result = self._parse_llm_response(response_text, current_problem)

            # ИСПРАВЛЕНО (2026-02-05): Добавляем флаг db_error в результат
            result['db_error'] = db_error

            # ИСПРАВЛЕНО (2026-01-05): КРИТИЧЕСКИ ВАЖНО - если is_meaningful=false, сохраняем current_problem!

            # ИСПРАВЛЕНО (2025-12-28): Детальный лог результата
            logger.info(f"[OK] ProblemAccumulation РЕЗУЛЬТАТ:")
            logger.info(
                f"ProblemAccumulation: '{message_text[:50]}...' → "
                f"'{result.get('updated_problem', current_problem)[:50]}...'"
            )

            return result

        except Exception as e:
            logger.error(f"Ошибка в ProblemAccumulationService: {e}")
            # В случае ошибки возвращаем текущее состояние без изменений
            return {
                'updated_problem': current_problem,
                'is_refusal': False,
                'refused_service': None,
                'db_error': False
            }

    async def _create_accumulation_prompt(
        self,
        message_text: str,
        current_problem: str,
        bot_question: str = None,
        dialog_history: List[Dict] = None
    ) -> str:
        """
        Создает промпт для LLM.

        ИСПРАВЛЕНО (2026-02-05): Загружает промпт из БД вместо хардкода.
        Если промпт не найден в БД - использует fallback с сообщением об ошибке.
        ИСПРАВЛЕНО (2026-02-05): Сделан async для работы с Django ORM через sync_to_async.
        ИСПРАВЛЕНО (2026-02-23): Удален history_context - дублирует current_problem и bot_question.
        """

        # ИСПРАВЛЕНО (2026-02-05): Загружаем промпт из БД
        try:
            from llm_tester.models import PromptTemplate
            from asgiref.sync import sync_to_async

            # ИСПРАВЛЕНО (2026-02-05): Используем sync_to_async для Django ORM
            @sync_to_async
            def get_db_template():
                return PromptTemplate.objects.filter(
                    slug='problem-accumulation-service',
                    is_active=True
                ).first()

            db_template = await get_db_template()

            if db_template:
                # Подставляем переменные в шаблон из БД (используем replace вместо format для JSON)
                prompt = db_template.template
                prompt = prompt.replace('{message_text}', message_text)
                prompt = prompt.replace('{current_problem}', current_problem if current_problem else '(пусто - начало диалога)')
                prompt = prompt.replace('{bot_question}', bot_question if bot_question else '(первое сообщение в диалоге)')

                logger.debug(f"[DB] Промпт загружен из БД (ID: {db_template.id})")
                return prompt
            else:
                logger.error(f"[DB] Промпт 'problem-accumulation-service' не найден в БД!")

        except Exception as e:
            logger.error(f"[DB] Ошибка загрузки промпта из БД: {e}")

        # Fallback-промпт с сообщением об ошибке (если промпт не найден в БД)
        logger.warning("[FALLBACK] Используется fallback-промпт (техническая ошибка!)")

        # ИСПРАВЛЕНО (2026-03-13): Fallback-промпт соответствует структуре из БД (3 поля)
        prompt = f"""Ты — аналитик, который накапливает описание проблемы по сообщениям пользователя в диалоге.

Входные данные:
- bot_question — последний вопрос бота
- current_problem — накопленное описание проблемы на предыдущих шагах
- message_text — новое сообщение пользователя

Данные:
bot_question: {bot_question if bot_question else '(первое сообщение в диалоге)'}
current_problem: {current_problem if current_problem else '(пусто - начало диалога)'}
message_text: {message_text}

Задача:
Определи, содержит ли message_text новую полезную информацию о проблеме, и обнови current_problem.

Правила принятия решения:

1) Когда is_meaningful = false
Ставь false, если сообщение не добавляет фактов о проблеме:
- приветствие, прощание, благодарность, вежливость: «привет», «спасибо», «пожалуйста», «ок»
- пустые/служебные ответы без фактов: «ага», «угу», «ну», «ясно»
- повтор current_problem без новых деталей
- сообщение не по теме проблемы

2) Когда is_meaningful = true
Ставь true, если сообщение:
- добавляет новый факт о проблеме (что случилось, где, что именно, степень, интенсивность и т.п.)
- является коротким ответом на вопрос бота и уточняет проблему (например: «в зале», «батарея», «горячей»)
- содержит ответ «да/нет», если это ответ на уточняющий вопрос бота и он меняет понимание проблемы

3) Критически важное правило сохранения current_problem
- Не теряй уже накопленные факты.
- Не перефразируй current_problem и не заменяй его синонимами.
- Добавляй только новую информацию.
- Разрешено только грамматически встроить уточнение в уже существующую фразу, если это нужно для корректного русского языка.
  Примеры логики (не выводить): «нет воды» + «горячей» => «нет горячей воды», «течет» + «батарея» => «течет батарея».
- Если current_problem = «(пусто)», создай описание с нуля по message_text.
- Если is_meaningful = false, updated_problem должен быть точной копией current_problem.

4) Критически важное правило отрицаний
Если в current_problem есть отрицание («нет», «не», «отсутствует»), обязательно сохрани это отрицание в updated_problem.
Нельзя превращать отрицание в нейтральную формулировку.
Нельзя заменять слова отрицания.

5) Ограничения на ответ
- Верни только JSON.
- Без markdown, без пояснений, без лишних полей.
- Ровно 3 ключа: is_meaningful, new_info, updated_problem.
- is_meaningful — boolean (true/false), не строка.
- new_info:
  - если is_meaningful=true: кратко опиши только новую информацию (5–10 слов)
  - если is_meaningful=false: напиши «новой информации о проблеме нет»
- updated_problem:
  - полное накопленное описание проблемы (1–2 предложения)
  - без выдуманных деталей
  - без потери ранее накопленных фактов

Формат ответа (строго):
{{
  "is_meaningful": true,
  "new_info": "краткое описание новой информации",
  "updated_problem": "полное обновленное описание проблемы"
}}"""
        return prompt

    def _parse_llm_response(self, response_text: str, current_problem: str = None) -> Dict[str, Any]:
        """
        Парсит ответ LLM и возвращает структурированный результат.

        ИСПРАВЛЕНО (2026-01-15): current_problem опционален для _is_refusal

        Args:
            response_text: Ответ от LLM
            current_problem: Текущее описание проблемы (опционально)

        Returns:
            Dict с распарсенными данными
        """
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
                'is_meaningful': result.get('is_meaningful', False),
                'new_info': result.get('new_info', ''),
                'is_refusal': False,
                'refused_service': None,
                'db_error': False
            }

        except json.JSONDecodeError as e:
            logger.error(f"Не удалось распарсить JSON из LLM ответа: {e}")
            logger.debug(f"Ответ LLM: {response_text[:500]}")
            # Возвращаем текущее состояние без изменений
            return {
                'updated_problem': current_problem,
                'is_meaningful': False,
                'new_info': '',
                'is_refusal': False,
                'refused_service': None,
                'db_error': False
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

    async def _is_refusal(self, text: str, context: str = None) -> bool:
        """
        ИСПРАВЛЕНО (2026-01-15): LLM-детектор отказа пользователя

        Проверяет через YandexGPT Lite является ли текст отказом от услуги.
        Отличает отказ от сообщения об отсутствии чего-либо.

        Args:
            text: Текст сообщения пользователя
            context: Контекст (предложенная услуга или ситуация)

        Returns:
            True если пользователь ОТКАЗЫВАЕТСЯ от услуги, иначе False

        Примеры:
        - "нет не это" → True (отказ)
        - "не подходит" → True (отказ)
        - "в кране нет горячей воды" → False (сообщение об отсутствии!)
        - "не приятно пахнет" → False (описание проблемы!)
        """
        if not text:
            return False

        try:
            # Формируем промпт для LLM
            prompt = f"""Ты - детектор отказов в диалоге с пользователем.

ТЕКСТ ПОЛЬЗОВАТЕЛЯ:
{text}

КОНТЕКСТ (что предложил бот или текущая ситуация):
{context if context else "неизвестно"}

ЗАДАЧА:
Определи - это ОТКАЗ от предложенной услуги/варианта ИЛИ сообщение о проблеме?

ПРАВИЛА:
1. ОТКАЗ - пользователь отвергает предложение: "нет не это", "не подходит", "это не то", "неверно"
2. НЕ ОТКАЗ - пользователь описывает проблему или отсутствие чего-то: "в кране нет воды", "не приятно пахнет", "нет горячей"
3. КРИТИЧЕСКИ ВАЖНО: "нет" в составе описания проблемы = НЕ ОТКАЗ!

ВЕРНИ JSON:
{{
  "is_refusal": true или false,
  "reasoning": "краткое обоснование"
}}

JSON:"""

            # ИСПРАВЛЕНО (2026-02-24): Передаем service_name для отслеживания
            response, _ = await self.ai_agent.call_llm(
                prompt=prompt,
                provider=None,  # Используем провайдер из env (DEFAULT_LLM_PROVIDER)
                model=None,  # Используем модель по умолчанию из .env
                caller_service='ProblemAccumulationService: RefusalCheck',
                prompt_source='runtime_generated'
            )

            # ИСПРАВЛЕНО (2026-01-15): Передаем current_problem=None (нет в контексте _is_refusal)
            result = self._parse_llm_response(response, current_problem=None)

            is_refusal = result.get('is_refusal', False)
            reasoning = result.get('reasoning', '')

            if is_refusal:
                logger.warning(f"[REFUSAL] LLM-детектор: ОТКАЗ (reasoning: {reasoning})")
            else:
                logger.info(f"[REFUSAL] LLM-детектор: НЕ отказ (reasoning: {reasoning})")

            return is_refusal

        except Exception as e:
            logger.warning(f"Ошибка LLM-детектора отказа: {e}, используем fallback")
            # Fallback на простую проверку
            return self._is_refusal_fallback(text)

    def _is_refusal_fallback(self, text: str) -> bool:
        """
        Fallback-детектор отказа на основе ключевых слов

        ИСПРАВЛЕНО (2026-01-15): Используется только если LLM недоступен

        Args:
            text: Текст сообщения пользователя

        Returns:
            True если текст содержит отказ, иначе False
        """
        if not text:
            return False

        # Явные маркеры отказа
        refusal_patterns = [
            r'\bнет\s+не\s+это\b',
            r'\bне\s+подходит\b',
            r'\bэто\s+не\s+то\b',
            r'\bне\s+то\b',
            r'\bошибаешься\b',
            r'\bошиблись\b',
            r'\bневерно\b'
        ]

        text_lower = text.lower().strip()

        # Проверяем паттерны
        for pattern in refusal_patterns:
            if re.search(pattern, text_lower):
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

        # ИСПРАВЛЕНО (2026-01-15): Убрано object_description!
        # Это поле устарело и не используется в новом промпте FilterDetectionService
        # Вся информация об объекте содержится в txtPrb
        # # СТАРЫЙ КОД (удален):
        # # Определяем object_description
        # obj = fields.get('object') or fields.get('source')
        # if obj:
        #     filters['object_description'] = {'value': obj, 'confidence': 0.95}

        return filters

    def _is_indoor_location(self, location: str) -> bool:
        """Определяет является ли локация индивидуальной (в квартире)."""
        indoor_keywords = ['ванной', 'кухн', 'зал', 'спальн', 'коридор', 'туалет', 'комнат']
        return any(keyword in location.lower() for keyword in indoor_keywords)
