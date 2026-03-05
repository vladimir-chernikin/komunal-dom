# НОВЫЙ ПОРЯДОК ВЫЗОВА СЕРВИСОВ
# Дата: 2026-02-23
# Путь к файлу: main_agent.py, строки ~343-500

# ============================================================
# БЛОК 1: Инициализация переменных
# ============================================================
txtPrb = ""
accumulated_fields = {}  # УБРАТЬ ПОСЛЕ РЕФАКТОРИНГА!
established_filters = {}

logger.info("[SEARCH] НАЧАЛО ОБРАБОТКИ:")
logger.info(f"  [NOTE] txtPrb: '{txtPrb[:80] if txtPrb else '(пусто)'}'")
logger.info(f"  [TOOL] established_filters: {established_filters}")

# ============================================================
# БЛОК 2: FilterDetectionService → established_filters (ПЕРВЫМ!)
# ============================================================
# КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: Вызываем ПЕРВЫМ, БЕЗ txtPrb!
semantic_check_result = {}
if self.filter_detection and self.ai_agent:
    try:
        logger.info("[РЕФАКТОРИНГ] ШАГ 1: FilterDetectionService (ПЕРВЫЙ!)")

        # ИСПРАВЛЕНО: Используем message_text БЕЗ txtPrb!
        # FilterDetectionService сам определит фильтры из сообщения
        semantic_check_result = await self._semantic_pre_check(
            message_text=message_text,  # БЕЗ txtPrb!
            dialog_history=dialog_history,
            txtPrb=None,  # ПУСТО!
            session_id=session_id,
            message_id=message_id
        )

        if semantic_check_result.get('filters'):
            established_filters = semantic_check_result['filters']
            logger.info(f"[РЕФАКТОРИНГ] ✅ established_filters: {established_filters}")
        else:
            logger.info("[РЕФАКТОРИНГ] FilterDetectionService не нашел фильтров")

    except Exception as e:
        logger.warning(f"Ошибка FilterDetectionService: {e}")
        semantic_check_result = {}

# ============================================================
# БЛОК 3: Mikroservices → candidates (С фильтрацией established_filters)
# ============================================================
# КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: Микросервисы вызываются ПОСЛЕ FilterDetectionService!
# С фильтрацией по established_filters
logger.info("[РЕФАКТОРИНГ] ШАГ 2: Микросервисы (С фильтрацией established_filters)")

# ... код запуска микросервисов ...
# TagSearchService, VectorSearchService, SemanticSearchService
# С фильтрацией по established_filters

# ============================================================
# БЛОК 4: ProblemAccumulationService → txtPrb (ПОСЛЕ микросервисов!)
# ============================================================
# КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: Вызываем ПОСЛЕ получения established_filters и candidates!
# txtPrb используется ТОЛЬКО для LLM Orchestrator
if self.problem_accumulator:
    try:
        logger.info("[РЕФАКТОРИНГ] ШАГ 3: ProblemAccumulationService (ПОСЛЕ микросервисов!)")

        # Извлекаем txtPrb из истории (если есть)
        if is_followup:
            txtPrb = self.problem_accumulator.get_txtPrb_from_metadata(dialog_history)
            logger.info(f"Текущий txtPrb из истории: '{txtPrb[:80] if txtPrb else '(пусто)'}...'")
        else:
            logger.info("Первое сообщение - начинаем накопление txtPrb")

        # Определяем последний вопрос бота
        last_bot_question = None
        if dialog_history:
            for msg in reversed(dialog_history[-3:]):
                if msg.get('role') == 'bot' and '?' in msg.get('text', ''):
                    last_bot_question = msg.get('text', '')
                    break

        # Накапливаем информацию
        accumulation_result = await self.problem_accumulator.extract_and_accumulate(
            message_text=message_text,
            current_problem=txtPrb,
            bot_question=last_bot_question,
            dialog_history=dialog_history,
            session_id=session_id,
            message_id=message_id
        )

        # Ошибка загрузки промпта
        if accumulation_result.get('db_error'):
            logger.error("[DB_ERROR] ProblemAccumulationService: ошибка загрузки промпта из БД!")
            return {
                'status': 'ERROR',
                'error': 'Ошибка загрузки промпта из базы данных',
                'message': 'Извините, произошла техническая ошибка. Попробуйте переформулировать.',
                'candidates': [],
                '_metadata': {
                    'txtPrb': txtPrb,
                    'db_error': True,
                    'error_type': 'prompt_db_error'
                }
            }

        # Обновляем txtPrb
        txtPrb = accumulation_result['updated_problem']

        # КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: accumulated_fields УБИРАЕМ!
        # accumulated_fields = accumulation_result.get('fields', {})  # УДАЛИТЬ!

        # Логирование
        logger.info(f"[РЕФАКТОРИНГ] ✅ txtPrb: '{txtPrb[:100]}'")
        logger.info(f"[РЕФАКТОРИНГ] ✅ established_filters: {established_filters}")

        # Обработка отказа
        if accumulation_result.get('is_refusal'):
            logger.warning(f"[REFUSAL] Пользователь отказался от услуги")
            logger.warning(f"[REFUSAL] txtPrb: '{txtPrb[:100]}'")

    except Exception as e:
        logger.warning(f"Ошибка ProblemAccumulationService: {e}")

# ============================================================
# БЛОК 5: LLM Orchestrator → вопрос (ВСЕГДА через LLM!)
# ============================================================
# КРИТИЧЕСКОЕ ИЗМЕНЕНИЕ: ВСЕГДА генерируем вопрос через LLM!
# 3 варианта промптов:
# - 0 candidates → промпт на основе txtPrb
# - 1 candidate conf>=0.9 → промпт на основе txtPrb + услуги
# - Несколько candidates → промпт на основе txtPrb + candidates

logger.info("[РЕФАКТОРИНГ] ШАГ 4: LLM Orchestrator (ВСЕГДА!)")

# ... код LLM Orchestrator ...

# ============================================================
# КОНЕЦ НОВОГО ПОРЯДКА
# ============================================================
