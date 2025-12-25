#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
IntelligentFilterService - интеллектуальная фильтрация запросов
Определяет категории, локализацию, тип инцидента для сужения поиска
"""

import logging
import re
import pymorphy2
from typing import Dict, List, Any, Optional
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class IntelligentFilterService:
    """Интеллектуальная фильтрация запросов"""

    def __init__(self):
        self.morph = None  # Ленивая инициализация
        self.service_categories = None
        self.filter_rules = self._load_filter_rules()
        logger.info("IntelligentFilterService инициализирован")

    def _get_morph(self):
        """Ленивая инициализация морфологического анализатора"""
        if self.morph is None:
            self.morph = pymorphy2.MorphAnalyzer()
        return self.morph

    def _load_filter_rules(self) -> Dict:
        """Загрузка правил фильтрации из catalog attributes вместо hardcoded правил"""
        # Загружаем уникальные значения из services_catalog
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT DISTINCT rc.category_name, rc.category_code
                        FROM ref_categories rc
                        JOIN services_catalog sc ON rc.category_id = sc.category_id
                        WHERE sc.is_active = TRUE
                    """)
                    categories = dict(cursor.fetchall())

                    cursor.execute("""
                        SELECT DISTINCT rk.kind_name, rk.kind_code
                        FROM ref_service_kinds rk
                        JOIN services_catalog sc ON rk.kind_id = sc.kind_id
                        WHERE sc.is_active = TRUE
                    """)
                    kinds = dict(cursor.fetchall())

                    cursor.execute("""
                        SELECT DISTINCT rl.localization_name
                        FROM ref_localization rl
                        JOIN services_catalog sc ON rl.localization_id = sc.localization_id
                        WHERE sc.is_active = TRUE
                    """)
                    localizations = [row[0] for row in cursor.fetchall()]

                    return {
                        'categories': categories,
                        'kinds': kinds,
                        'localizations': localizations,
                        'use_catalog_attributes': True
                    }

            return sync_to_async(load_sync)()

        except Exception as e:
            logger.error(f"Ошибка загрузки атрибутов каталога: {e}")
            return {
                'categories': {},
                'kinds': {},
                'localizations': [],
                'use_catalog_attributes': False
            }

    async def analyze_request(self, text: str, context: Dict = None) -> Dict:
        """
        Интеллектуальный анализ запроса

        Args:
            text: Текст запроса пользователя
            context: Дополнительный контекст (предыдущие сообщения)

        Returns:
            Dict: Результаты фильтрации
        """
        try:
            logger.info(f"IntelligentFilter: анализ текста '{text}'")

            # Нормализация текста
            morph = self._get_morph()
            text_lower = text.lower()
            words = re.findall(r'\b\w+\b', text_lower)
            normalized_words = [morph.parse(w)[0].normal_form for w in words]

            # Определение фильтров
            filters = {
                'incident_type': self._detect_incident_type(text_lower, normalized_words),
                'problem_category': self._detect_problem_category(text_lower, normalized_words),
                'location_type': self._detect_location_type(text_lower, normalized_words),
                'utility_system': self._detect_utility_system(text_lower, normalized_words),
                'urgency_level': self._detect_urgency(text_lower, normalized_words),
                'clarifications_needed': self._detect_needed_clarifications(text_lower, normalized_words)
            }

            # Применение контекстных правил
            if context:
                filters = self._apply_context_rules(filters, context)

            # Формирование фильтрованного набора услуг
            filtered_services = self._get_filtered_services(filters)

            result = {
                'status': 'success',
                'filters': filters,
                'filtered_service_ids': filtered_services,
                'analysis_details': {
                    'original_text': text,
                    'normalized_words': normalized_words,
                    'confidence_scores': self._calculate_filter_confidence(filters, text_lower)
                }
            }

            logger.info(f"IntelligentFilter: определены фильтры - {filters}")
            return result

        except Exception as e:
            logger.error(f"Ошибка в IntelligentFilterService: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'filtered_service_ids': []
            }

    def _detect_incident_type(self, text: str, normalized_words: List[str]) -> Dict:
        """Определение типа инцидента"""
        incident_scores = {}

        for incident_type, rules in self.filter_rules['incident_types'].items():
            score = 0.0

            # Проверка ключевых слов
            for keyword in rules['keywords']:
                if keyword in text:
                    score += rules['weight']

            # Проверка паттернов
            for pattern in rules.get('patterns', []):
                if re.search(pattern, text):
                    score += rules['weight'] * 1.2

            # Проверка нормализованных слов
            for word in normalized_words:
                for keyword in rules['keywords']:
                    if word == keyword:
                        score += rules['weight'] * 0.8

            incident_scores[incident_type] = min(score, 1.0)

        # Выбор типа с максимальным счетом
        best_type = max(incident_scores, key=incident_scores.get)
        confidence = incident_scores[best_type]

        return {
            'type': best_type if confidence > 0.2 else 'unknown',
            'confidence': confidence,
            'all_scores': incident_scores
        }

    def _detect_problem_category(self, text: str, normalized_words: List[str]) -> Dict:
        """Определение категории проблемы"""
        category_scores = {}

        for category, rules in self.filter_rules['problem_categories'].items():
            score = 0.0

            # Проверка ключевых слов
            for keyword in rules['keywords']:
                if keyword in text:
                    score += 1.0

            # Проверка нормализованных слов
            for word in normalized_words:
                for keyword in rules['keywords']:
                    if word == keyword:
                        score += 0.9

            category_scores[category] = score

        if not category_scores or max(category_scores.values()) < 0.3:
            return {
                'category': 'unknown',
                'confidence': 0.0,
                'utility_system': None,
                'urgency': 'medium'
            }

        # Выбор категории с максимальным счетом
        best_category = max(category_scores, key=category_scores.get)
        confidence = category_scores[best_category] / len(self.filter_rules['problem_categories'][best_category]['keywords'])
        category_rules = self.filter_rules['problem_categories'][best_category]

        return {
            'category': best_category,
            'confidence': min(confidence, 1.0),
            'utility_system': category_rules.get('utility_system'),
            'urgency': category_rules.get('urgency', 'medium'),
            'service_ids': category_rules.get('service_ids', [])
        }

    def _detect_location_type(self, text: str, normalized_words: List[str]) -> Dict:
        """Определение типа локации"""
        location_scores = {}

        for location_type, rules in self.filter_rules['location_types'].items():
            if location_type == 'unknown':
                continue

            score = 0.0

            # Проверка ключевых слов
            for keyword in rules['keywords']:
                if keyword in text:
                    score += rules['weight']

            # Проверка паттернов
            for pattern in rules.get('patterns', []):
                if re.search(pattern, text):
                    score += rules['weight'] * 1.3

            # Проверка нормализованных слов
            for word in normalized_words:
                for keyword in rules['keywords']:
                    if word == keyword:
                        score += rules['weight'] * 0.7

            location_scores[location_type] = score

        # Выбор локации с максимальным счетом
        if not location_scores or max(location_scores.values()) < 0.3:
            best_type = 'unknown'
            confidence = 0.0
            scope = 'UNKNOWN'
        else:
            best_type = max(location_scores, key=location_scores.get)
            confidence = min(location_scores[best_type] / 2.0, 1.0)  # Нормализация
            scope = self.filter_rules['location_types'][best_type]['scope']

        return {
            'type': best_type,
            'scope': scope,
            'confidence': confidence,
            'clarification_needed': best_type == 'unknown'
        }

    def _detect_utility_system(self, text: str, normalized_words: List[str]) -> Dict:
        """Определение системы коммуникаций"""
        system_scores = {}

        for system, rules in self.filter_rules['utility_systems'].items():
            score = 0.0

            # Проверка ключевых слов
            for keyword in rules['keywords']:
                if keyword in text:
                    score += 1.0

            # Проверка нормализованных слов
            for word in normalized_words:
                for keyword in rules['keywords']:
                    if word == keyword:
                        score += 0.8

            system_scores[system] = score

        if not system_scores or max(system_scores.values()) < 0.2:
            return {'system': 'unknown', 'subsystem': None, 'confidence': 0.0}

        # Выбор системы с максимальным счетом
        best_system = max(system_scores, key=system_scores.get)
        confidence = min(system_scores[best_system] / 3.0, 1.0)  # Нормализация

        # Определение подсистемы
        subsystem = None
        system_rules = self.filter_rules['utility_systems'][best_system]
        for sub in system_rules.get('subsystems', []):
            if sub in text:
                subsystem = sub
                break

        return {
            'system': best_system,
            'subsystem': subsystem,
            'confidence': confidence
        }

    def _detect_urgency(self, text: str, normalized_words: List[str]) -> Dict:
        """Определение уровня срочности"""
        urgent_keywords = ['срочно', 'немедленно', 'авария', 'пробило', 'затапливает', 'пожар']
        medium_keywords = ['нужно', 'требуется', 'проблема', 'не работает', 'сломалось']
        low_keywords = ['проверить', 'посмотреть', 'когда', 'в ближайшее время']

        text_lower = text.lower()

        if any(keyword in text_lower for keyword in urgent_keywords):
            return {'level': 'high', 'priority': 1, 'reason': 'urgent_keywords'}
        elif any(keyword in text_lower for keyword in medium_keywords):
            return {'level': 'medium', 'priority': 2, 'reason': 'medium_keywords'}
        elif any(keyword in text_lower for keyword in low_keywords):
            return {'level': 'low', 'priority': 3, 'reason': 'low_keywords'}
        else:
            return {'level': 'medium', 'priority': 2, 'reason': 'default'}

    def _detect_needed_clarifications(self, text: str, normalized_words: List[str]) -> List[str]:
        """Определение необходимых уточнений"""
        clarifications = []

        # Неопределенный тип системы
        if 'труба' in normalized_words and not any(sys in text for sys in ['вода', 'отопление', 'канализация']):
            clarifications.append('utility_system_type')

        # Неопределенная локация
        if not any(loc in text for loc in ['квартира', 'подъезд', 'подвал', 'общее']):
            clarifications.append('location_type')

        # Нет конкретики проблемы
        if 'проблема' in normalized_words or len(normalized_words) < 3:
            clarifications.append('problem_details')

        return clarifications

    def _apply_context_rules(self, filters: Dict, context: Dict) -> Dict:
        """Применение контекстных правил"""
        # TODO: Реализовать контекстные правила
        return filters

    def _get_filtered_services(self, filters: Dict) -> List[int]:
        """Получение отфильтрованного списка ID услуг"""
        # Начинаем с Problem Category сервисов
        problem_services = filters.get('problem_category', {}).get('service_ids', [])

        if problem_services:
            return problem_services

        # Если нет конкретных услуг, возвращаем пустой список для полного поиска
        return []

    def _calculate_filter_confidence(self, filters: Dict, text: str) -> Dict:
        """Расчет уверенности фильтров"""
        return {
            'incident_type_confidence': filters.get('incident_type', {}).get('confidence', 0.0),
            'problem_category_confidence': filters.get('problem_category', {}).get('confidence', 0.0),
            'location_type_confidence': filters.get('location_type', {}).get('confidence', 0.0),
            'overall_confidence': self._calculate_overall_confidence(filters)
        }

    def _calculate_overall_confidence(self, filters: Dict) -> float:
        """Расчет общей уверенности в фильтрации"""
        incident_conf = filters.get('incident_type', {}).get('confidence', 0.0)
        problem_conf = filters.get('problem_category', {}).get('confidence', 0.0)
        location_conf = filters.get('location_type', {}).get('confidence', 0.0)

        # Взвешенная оценка
        weights = {
            'incident_type': 0.3,
            'problem_category': 0.5,
            'location_type': 0.2
        }

        overall = (incident_conf * weights['incident_type'] +
                  problem_conf * weights['problem_category'] +
                  location_conf * weights['location_type'])

        return min(overall, 1.0)