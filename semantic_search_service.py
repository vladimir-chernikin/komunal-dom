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
                    'вода', 'течет', 'протекает', 'прорыв', 'утечка',
                    'засор', 'канализация', 'сантехника', 'кран',
                    'смеситель', 'раковина', 'унитаз', 'туалет'
                ],
                'weight': 0.9
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
                    'крыша', 'кровля', 'течет', 'протекает', 'затекает',
                    'чердачек', 'желоб', 'водосток'
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
                # Рассчитываем уверенность для этого признака
                confidence = min(total_matches / len(feature_data['keywords']), 1.0)
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
        """
        service_scores = {}

        for service_id, service_info in self.service_cache.items():
            score = 0.0
            reasons = []

            # Анализ по типу (incident_type)
            if 'incident' in features:
                if service_info.get('incident_type') == 'Инцидент':
                    score += features['incident']['confidence'] * 0.6
                    reasons.append('emergency_incident')

            if 'request' in features:
                if service_info.get('incident_type') == 'Запрос':
                    score += features['request']['confidence'] * 0.6
                    reasons.append('service_request')

            # Анализ по категории (category) - увеличен вес
            category_matches = {
                'water': ['Водоснабжение', 'Санитария'],
                'electricity': ['Электричество'],
                'heating': ['Отопление'],
                'construction': ['Ремонт МАФ и покрытий', 'Конструктив'],
                'cleaning': ['Санитария'],
                'landscape': ['Озеленение'],
                'elevator': ['Лифты'],
                'roof': ['Конструктив']
            }

            for category, cat_keywords in category_matches.items():
                if category in features:
                    category_lower = (service_info.get('category') or '').lower()
                    name_lower = (service_info.get('scenario_name') or '').lower()
                    for keyword in cat_keywords:
                        if keyword.lower() in category_lower or keyword.lower() in name_lower:
                            score += features[category]['confidence'] * 0.5
                            reasons.append(f'{category}_match')
                            break

            # ИСПРАВЛЕНО: Анализ по локации (location_type) - ТОЛЬКО если пользователь указал локацию
            # НЕ наказываем услуги если пользователь не сказал где именно проблема

            if score > 0:
                service_scores[service_id] = min(score, 1.0)
                logger.debug(f"Service {service_id} ({service_info['scenario_name']}): {score:.3f} - {', '.join(reasons)}")

        return service_scores

    async def search(self, message_text: str) -> Dict:
        """
        Основной метод семантического поиска

        Args:
            message_text: Текст сообщения пользователя

        Returns:
            Dict: Результат поиска в формате JSON {[КодУслуги], [Релевантность]}
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

            # Конвертируем в нужный формат JSON
            candidates = []
            for service_id, confidence in service_scores.items():
                if confidence >= 0.2:  # ИСПРАВЛЕНО: Снижен порог с 0.3 до 0.2
                    service_name = self.service_cache[service_id]['scenario_name']
                    candidates.append({
                        'service_id': service_id,
                        'service_name': service_name,
                        'confidence': round(confidence, 3),
                        'source': 'semantic_search'
                    })

            # Сортируем по уверенности убыванию
            candidates.sort(key=lambda x: x['confidence'], reverse=True)

            result = {
                'status': 'success',
                'candidates': candidates[:5],
                'semantic_features': features,
                'total_matches': len(candidates),
                'method': 'semantic_search'
            }

            logger.info(f"SemanticSearch: найдено услуг: {len(candidates)}")
            return result

        except Exception as e:
            logger.error(f"Ошибка в SemanticSearchService: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'candidates': []
            }
