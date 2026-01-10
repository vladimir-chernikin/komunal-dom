#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SemanticSearchService - логико-семантический микросервис поиска услуг
Использует справочные таблицы (ref_*) для семантического анализа
"""

import logging
import re
from typing import List, Dict, Set
from django.db import connection
from asgiref.sync import sync_to_async
import pymorphy2

logger = logging.getLogger(__name__)


class SemanticSearchService:
    """Микросервис логико-семантического поиска услуг"""

    def __init__(self):
        self.service_cache = None
        self.morph = None
        self.semantic_patterns = self._init_semantic_patterns()
        self._ensure_patterns_normalized()
        logger.info("SemanticSearchService инициализирован с морфологией")

    def _get_morph(self):
        """Ленивая инициализация морфологического анализатора"""
        if self.morph is None:
            self.morph = pymorphy2.MorphAnalyzer()
        return self.morph

    def _calculate_adaptive_threshold(self, message_text: str) -> tuple:
        """
        Адаптивный расчет порога и лимита в зависимости от длины запроса

        ИСПРАВЛЕНО (2025-12-25): Адаптивный порог вместо фиксированного 0.2
        ИСПРАВЛЕНО (2025-12-26): Увеличены пороги для уменьшения ложных срабатываний

        Args:
            message_text: Текст сообщения

        Returns:
            tuple: (threshold, limit) - порог уверенности и лимит результатов
        """
        # Считаем количество слов
        words = message_text.strip().split()
        word_count = len(words)

        # Считаем количество символов
        char_count = len(message_text.strip())

        # Определяем категорию запроса (ИСПРАВЛЕНО: повышены пороги)
        if word_count <= 2 and char_count < 15:
            # Короткий запрос: "у меня течет", "сломался"
            # ИСПРАВЛЕНО: 0.10 -> 0.25 чтобы отсекать слабые совпадения
            threshold = 0.25
            limit = 3
            category = "короткий"
        elif word_count <= 5 and char_count < 40:
            # Средний запрос: "у меня прорвало трубу в ванной"
            # ИСПРАВЛЕНО: 0.15 -> 0.30
            threshold = 0.30
            limit = 5
            category = "средний"
        else:
            # Длинный запрос: подробное описание проблемы
            # ИСПРАВЛЕНО: 0.20 -> 0.35
            threshold = 0.35
            limit = 7
            category = "длинный"

        logger.info(
            f"SemanticSearch: запрос '{message_text[:30]}...' -> "
            f"категория='{category}' (слов:{word_count}, символов:{char_count}), "
            f"порог={threshold}, лимит={limit}"
        )

        return threshold, limit

    def _init_semantic_patterns(self) -> Dict:
        """Инициализация семантических паттернов для анализа"""
        return {
            'incident': {
                'definition': 'Проблема, требующая решения',
                'keywords': [
                    'проблема', 'сломался', 'не работает', 'поломка', 'авария',
                    'утечка', 'течет', 'протекает', 'прорыв', 'засор',
                    'нет', 'отсутствует', 'выключено', 'перебой'
                ],
                'weight': 0.9
            },
            'request': {
                'definition': 'Запрос на информацию или услугу',
                'keywords': [
                    'хочу', 'нужно', 'пожалуйста', 'подскажите',
                    'как', 'что', 'где', 'когда', 'почему'
                ],
                'weight': 0.7
            },
            'water': {
                'definition': 'Проблемы с водоснабжением',
                'keywords': [
                    'вода', 'кран', 'водопровод', 'смеситель', 'раковина',
                    'унитаз', 'туалет', 'смыв', 'насос', 'вода',
                    'горячая вода', 'холодная вода', 'напор'
                ],
                'weight': 0.9
            },
            'leak': {
                'definition': 'Утечка, протечка, прорыв',
                'keywords': [
                    'течет', 'протекает', 'прорыв', 'утечка', 'капает',
                    'льется', 'текут', 'вытекает'
                ],
                'weight': 0.95
            },
            'electricity': {
                'definition': 'Проблемы с электричеством',
                'keywords': [
                    'свет', 'электричество', 'лампочка', 'выключило',
                    'розетка', 'провод', 'короткое', 'замыкание',
                    'искрит', 'нет света', 'темно'
                ],
                'weight': 0.9
            },
            'heating': {
                'definition': 'Проблемы с отоплением',
                'keywords': [
                    'отопление', 'батарея', 'радиатор', 'тепло', 'холодно',
                    'не греет', 'стояк', 'теплотрасса'
                ],
                'weight': 0.9
            },
            'construction': {
                'definition': 'Строительные и ремонтные работы',
                'keywords': [
                    'ремонт', 'стройка', 'покраска', 'отделка', 'асфальт',
                    'дверь', 'окно', 'стена', 'пол', 'потолок'
                ],
                'weight': 0.8
            },
            'cleaning': {
                'definition': 'Уборка и санитарные работы',
                'keywords': [
                    'уборка', 'мусор', 'чистка', 'вывоз', 'контейнер',
                    'свояк', 'грязь', 'санитария'
                ],
                'weight': 0.8
            },
            'landscape': {
                'definition': 'Благоустройство и озеленение',
                'keywords': [
                    'дерево', 'газон', 'куст', 'трава', 'цветок', 'парк',
                    'сквер', 'лужайка', 'зеленый'
                ],
                'weight': 0.7
            },
            'elevator': {
                'definition': 'Проблемы с лифтом',
                'keywords': [
                    'лифт', 'лифта', 'кабина', 'кнопка', 'этаж',
                    'застрял', 'не работает', 'заблокирован'
                ],
                'weight': 0.95
            },
            'roof': {
                'definition': 'Проблемы с крышей',
                'keywords': [
                    'крыша', 'кровля', 'затекает',  # УБРАНО: 'течет', 'протекает' (без контекста крыши!)
                    'чердачек', 'желоб', 'водосток', 'потекает',
                    'крыши', 'потолок'  # Добавлено уточнение
                ],
                'weight': 0.9
            },
            'inside': {
                'definition': 'Внутри помещения (квартира)',
                'keywords': [
                    'квартира', 'в квартире', 'моя', 'домой', 'в доме',
                    'внутри', 'помещение', 'комната'
                ],
                'weight': 0.8
            },
            'outside': {
                'definition': 'Общедомовое имущество',
                'keywords': [
                    'подъезд', 'лифт', 'подвал', 'крыша', 'чердак',
                    'общее', 'общедом', 'двор', 'территория'
                ],
                'weight': 0.8
            }
        }

    def _ensure_patterns_normalized(self) -> bool:
        """Нормализует ключевые слова в семантических паттернах"""
        if hasattr(self, '_patterns_normalized'):
            return self._patterns_normalized

        try:
            morph = self._get_morph()
            for pattern_name, pattern_data in self.semantic_patterns.items():
                normalized_keywords = []
                for keyword in pattern_data['keywords']:
                    # Нормализуем каждое ключевое слово
                    words = re.findall(r'\b\w+\b', keyword.lower())
                    for word in words:
                        parsed = morph.parse(word)[0]
                        normalized_keywords.append(parsed.normal_form)

                # Добавляем нормализованные ключевые слова
                pattern_data['normalized_keywords'] = list(set(normalized_keywords))

            self._patterns_normalized = True
            return True

        except Exception as e:
            logger.error(f"Ошибка нормализации паттернов: {e}")
            return False

    async def _load_services(self) -> Dict:
        """
        Асинхронная загрузка услуг из БД
        ИСПРАВЛЕНО: Использует денормализованные колонки (incident_type, category, location_type)
        """
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # ИСПРАВЛЕНО: Используем денормализованные колонки напрямую
                    cursor.execute("""
                        SELECT service_id, scenario_name, description_for_search,
                               incident_type, category, location_type
                        FROM services_catalog
                        WHERE is_active = TRUE
                    """)
                    results = cursor.fetchall()

                services = {}
                for service_id, scenario_name, description, incident_type, category, location_type in results:
                    services[service_id] = {
                        'service_id': service_id,
                        'scenario_name': scenario_name,
                        'description': description or scenario_name,
                        'incident_type': incident_type or '',
                        'category': category or '',
                        'location_type': location_type or ''
                    }

                return services

            self.service_cache = await sync_to_async(load_sync)()
            logger.info(f"SemanticSearchService: загружено {len(self.service_cache)} услуг из services_catalog")

        except Exception as e:
            logger.error(f"Ошибка загрузки услуг: {e}")
            self.service_cache = {}

    def _analyze_semantic_features(self, text: str) -> Dict:
        """Анализ семантических признаков текста с морфологией"""
        features = {}

        # Нормализуем текст сообщения
        self._ensure_patterns_normalized()
        morph = self._get_morph()

        text_words = re.findall(r'\b\w+\b', text.lower())
        normalized_text_words = []
        for word in text_words:
            parsed = morph.parse(word)[0]
            normalized_text_words.append(parsed.normal_form)

        text_lower = text.lower()
        normalized_text = ' '.join(normalized_text_words)

        logger.info(f"SemanticSearch: исходный текст '{text}' -> нормализованный '{normalized_text}'")

        # Анализируем каждый семантический разрез
        for feature_name, feature_data in self.semantic_patterns.items():
            matches = 0
            matched_keywords = []
            normalized_matches = 0

            # Проверяем точные совпадения с оригинальными ключевыми словами
            for keyword in feature_data['keywords']:
                if keyword in text_lower:
                    matches += 1
                    matched_keywords.append(keyword)

            # Проверяем совпадения с нормализованными ключевыми словами
            normalized_keywords = feature_data.get('normalized_keywords', [])
            for norm_word in normalized_text_words:
                if norm_word in normalized_keywords:
                    normalized_matches += 1

            # Учитываем оба типа совпадений
            total_matches = matches + normalized_matches
            if total_matches > 0:
                # ИСПРАВЛЕНО (2026-01-06): Для коротких запросов учитываем сами совпадения, не деля на количество keywords
                # Старая логика: confidence = (total_matches / len(keywords)) * weight
                # Проблема: 1 совпадение из 10 keywords = 0.1 * 0.9 = 0.09 (слишком мало!)

                # Новая логика: каждое совпадение дает вес, нормализуем на максимально возможное
                max_possible_matches = min(len(feature_data['keywords']), 3)  # Максимум 3 совпадения учитываем
                confidence = min(total_matches / max_possible_matches, 1.0)
                confidence *= feature_data['weight']

                features[feature_name] = {
                    'confidence': round(confidence, 3),
                    'matches': matches,
                    'normalized_matches': normalized_matches,
                    'total_matches': total_matches,
                    'keywords': matched_keywords,
                    'definition': feature_data['definition']
                }

        return features

    def _match_features_to_services(self, features: Dict) -> Dict[int, float]:
        """
        Сопоставляет семантические признаки с услугами
        ИСПРАВЛЕНО: Использует денормализованные колонки (incident_type, category, location_type)
        ИСПРАВЛЕНО: НЕ требует обязательного совпадения по location_type если пользователь не указал локацию
        ИСПРАВЛЕНО (2025-12-26): Добавлена проверка на соответствие ОБЕИМ признакам (incident + category)
        """
        service_scores = {}

        for service_id, service_info in self.service_cache.items():
            score = 0.0
            reasons = []

            # ИСПРАВЛЕНИЕ: Проверяем что услуга соответствует ОБЩИМ признакам, не только incident_type
            # Если есть признак категории (water, electricity, etc.) - услуга ДОЛЖНА к ней относиться

            # Определяем требуемые категории из features
            required_categories = set()
            if 'water' in features:
                required_categories.update(['Водоснабжение', 'Санитария'])
            if 'leak' in features:
                # ИСПРАВЛЕНО (2026-01-10): 'leak' может относиться к ЛЮБОЙ категории где есть трубы/системы
                # Водоснабжение, Отопление, Канализация, Конструктив (крыша)
                required_categories.update(['Водоснабжение', 'Отопление', 'Канализация', 'Конструктив'])
            if 'electricity' in features:
                required_categories.add('Электричество')
            if 'heating' in features:
                required_categories.add('Отопление')
            if 'construction' in features:
                required_categories.update(['Ремонт МАФ и покрытий', 'Конструктив'])
            if 'cleaning' in features:
                required_categories.add('Санитария')
            if 'landscape' in features:
                required_categories.add('Озеленение')
            if 'elevator' in features:
                required_categories.add('Лифты')
            if 'roof' in features:
                required_categories.add('Конструктив')

            # Если есть требуемые категории - проверяем соответствие
            # ИСПРАВЛЕНО (2026-01-10): ВСЕГДА проверяем категорию, даже если required_categories пусто!
            # Если признаки детектированы (incident, water, etc.) - услуга ДОЛЖНА соответствовать хотя бы одному

            service_category = (service_info.get('category') or '').strip()
            service_name = (service_info.get('scenario_name') or '').strip()
            service_incident = service_info.get('incident_type', '')

            # ИСПРАВЛЕНО (2026-01-10): КРИТИЧЕСКИ ВАЖНО!
            # Если есть features БЕЗ категории (например, только 'incident' без 'water'),
            # то НЕ добавляем балл за incident если категория услуги не совпадает!
            # Это предотвращает 66% для ЛЮБОЙ услуги с incident_type='Инцидент'

            should_add_incident_score = True  # По умолчанию добавляем

            # Если есть признак incident НО нет признаков категории (water, heating, etc.)
            if 'incident' in features and not any(f in features for f in ['water', 'electricity', 'heating', 'construction', 'cleaning', 'landscape', 'elevator', 'roof']):
                # НЕ добавляем балл incident если категория услуги неочевидна
                # Это отсечёт случайные совпадения
                should_add_incident_score = False
                logger.debug(f"Service {service_id}: incident БЕЗ категории - пропускаем (service_category={service_category})")

            # Если есть требуемые категории - проверяем соответствие
            if required_categories:
                # Проверяем что услуга относится хотя бы к одной требуемой категории
                category_match = any(
                    cat.lower() in service_category.lower() or cat.lower() in service_name.lower()
                    for cat in required_categories
                )

                if not category_match:
                    # Услуга не соответствует требуемым категориям - пропускаем
                    continue

            # Анализ по типу (incident_type)
            # ИСПРАВЛЕНО (2026-01-10): Добавляем балл ТОЛЬКО если should_add_incident_score=True
            if 'incident' in features and should_add_incident_score:
                if service_info.get('incident_type') == 'Инцидент':
                    score += features['incident']['confidence'] * 0.6
                    reasons.append('emergency_incident')

            if 'request' in features:
                if service_info.get('incident_type') == 'Запрос':
                    score += features['request']['confidence'] * 0.6
                    reasons.append('service_request')

            # ИСПРАВЛЕНО (2026-01-10): Уточненная логика маппинга признаков на категории
            # СТАРАЯ ЛОГИКА: Если category в списке → score (ЛОЖНЫЕ СОВПАДЕНИЯ!)
            # НОВАЯ ЛОГИКА: Если СЛОВА ПРИЗНАКА в названии/описании → score (ТОЧНО!)
            for feature_key, feature_data in features.items():
                if feature_key in self.semantic_patterns:
                    pattern_keywords = self.semantic_patterns[feature_key]['keywords']
                    name_lower = (service_info.get('scenario_name') or '').lower()
                    desc_lower = (service_info.get('description_for_search') or '').lower()

                    # Проверяем есть ли СЛОВА ПРИЗНАКА в названии или описании услуги
                    for keyword in pattern_keywords:
                        keyword_lower = keyword.lower()
                        if keyword_lower in name_lower or keyword_lower in desc_lower:
                            score += feature_data['confidence'] * 0.5
                            reasons.append(f'{feature_key}_match')
                            break  # Только первое совпадение

            # ИСПРАВЛЕНО: Анализ по локации (location_type) - ТОЛЬКО если пользователь указал локацию
            # НЕ наказываем услуги если пользователь не сказал где именно проблема

            if score > 0:
                service_scores[service_id] = min(score, 1.0)
                logger.debug(f"Service {service_id} ({service_info['scenario_name']}): {score:.3f} - {', '.join(reasons)}")

        return service_scores

    async def search(self, message_text: str, filters: Dict = None) -> Dict:
        """
        Основной метод семантического поиска

        Args:
            message_text: Текст сообщения пользователя
            filters: Словарь фильтров для применения к кандидатам
                     {'incident_type': 'Инцидент', 'location_type': 'Индивидуальное', 'category': 'Водоснабжение'}

        Returns:
            Dict: Результат поиска в формате JSON {[КодУслуги], [Релевантность]}

        ИСПРАВЛЕНО (2026-01-10): Добавлен параметр filters и логика фильтрации candidates
        """
        try:
            logger.info(f"SemanticSearch: анализ текста '{message_text[:50]}...'")

            # Загружаем услуги если еще не загружены
            if self.service_cache is None:
                await self._load_services()

            if not self.service_cache:
                return {'candidates': [], 'error': 'Услуги не загружены'}

            # Анализируем семантические признаки
            features = self._analyze_semantic_features(message_text)

            if not features:
                logger.info("SemanticSearch: семантических признаков не найдено")
                return {'candidates': []}

            logger.info(f"SemanticSearch: найдено признаков: {list(features.keys())}")

            # Сопоставляем признаки с услугами
            service_scores = self._match_features_to_services(features)

            if not service_scores:
                return {'candidates': []}

            # ИСПРАВЛЕНО (2025-12-25): Адаптивный порог и ТОП-N
            threshold, limit = self._calculate_adaptive_threshold(message_text)

            # Конвертируем в нужный формат JSON с адаптивным порогом
            # ИСПРАВЛЕНО (2025-12-26): Добавлены incident_type, category, location_type
            candidates = []
            for service_id, confidence in service_scores.items():
                if confidence >= threshold:  # Адаптивный порог
                    service_data = self.service_cache[service_id]
                    service_name = service_data['scenario_name']
                    candidates.append({
                        'service_id': service_id,
                        'service_name': service_name,
                        'confidence': round(confidence, 3),
                        'source': 'semantic_search',
                        'incident_type': service_data.get('incident_type', ''),
                        'category': service_data.get('category', ''),
                        'location_type': service_data.get('location_type', '')
                    })

            # Сортируем по уверенности убыванию и берем ТОП-N
            candidates.sort(key=lambda x: x['confidence'], reverse=True)

            # ИСПРАВЛЕНО (2026-01-10): Применяем фильтры к кандидатам
            # ИСПРАВЛЕНО (2026-01-10): Извлекаем .get('value') из словаря фильтров
            if filters:
                before_count = len(candidates)
                filtered = candidates

                # Helper функция для извлечения значения из фильтра
                def get_filter_value(filter_key):
                    """Извлекает value из фильтра, который может быть строкой или dict {'value': ..., 'confidence': ...}"""
                    filter_data = filters.get(filter_key)
                    if filter_data is None:
                        return None
                    if isinstance(filter_data, dict):
                        return filter_data.get('value')
                    return filter_data

                incident_value = get_filter_value('incident_type')
                if incident_value:
                    filtered = [c for c in filtered
                               if incident_value in c.get('incident_type', '')]
                    logger.info(f"SemanticSearch: Отфильтровано по incident_type={incident_value}: {len(filtered)} из {before_count}")

                location_value = get_filter_value('location_type')
                if location_value:
                    filtered = [c for c in filtered
                               if location_value in c.get('location_type', '')]
                    logger.info(f"SemanticSearch: Отфильтровано по location_type={location_value}: {len(filtered)} из {before_count}")

                category_value = get_filter_value('category')
                if category_value:
                    filtered = [c for c in filtered
                               if category_value.lower() in c.get('category', '').lower()]
                    logger.info(f"SemanticSearch: Отфильтровано по category={category_value}: {len(filtered)} из {before_count}")

                candidates = filtered

            result = {
                'status': 'success',
                'candidates': candidates[:limit],  # Адаптивный лимит
                'semantic_features': features,
                'total_matches': len(candidates),
                'method': 'semantic_search'
            }

            logger.info(f"SemanticSearch: найдено услуг: {len(candidates)} (порог: {threshold}, лимит: {limit})")
            return result

        except Exception as e:
            logger.error(f"Ошибка в SemanticSearchService: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'candidates': []
            }
