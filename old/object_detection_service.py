#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ObjectDetectionService - сервис определения объектов обслуживания
Анализирует адрес из сообщения пользователя и находит соответствующие объекты в БД
"""

import logging
import re
import pymorphy2
from typing import List, Dict, Any, Optional, Tuple
from django.db import connection
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)


class ObjectDetectionService:
    """Сервис определения объектов обслуживания"""

    def __init__(self):
        self.morph = None  # Ленивая инициализация
        self.building_cache = None
        self.service_objects_cache = None
        logger.info("ObjectDetectionService инициализирован")

    def _get_morph(self):
        """Ленивая инициализация морфологического анализатора"""
        if self.morph is None:
            self.morph = pymorphy2.MorphAnalyzer()
        return self.morph

    async def _load_buildings(self):
        """Загрузка зданий из БД"""
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    # Загружаем здания с адресами из КЛАДР
                    cursor.execute("""
                        SELECT b.building_id, b.house_number, b.parent_ao_id, b.kladr_code,
                               ao.name, ao.kladr_level
                        FROM buildings b
                        LEFT JOIN kladr_address_objects ao ON b.parent_ao_id = ao.ao_id
                        WHERE b.is_active = TRUE
                        ORDER BY ao.kladr_level, b.house_number
                    """)
                    results = cursor.fetchall()

                building_cache = {}
                for row in results:
                    building_id, house_number, parent_ao_id, kladr_code, name, kladr_level = row

                    building_cache[building_id] = {
                        'building_id': building_id,
                        'house_number': house_number.lower().strip(),
                        'parent_ao_id': parent_ao_id,
                        'kladr_code': kladr_code,
                        'name': name.lower() if name else '',
                        'kladr_level': kladr_level,
                        # Формируем полный адрес для поиска
                        'full_address': f"{name or ''} {house_number}".lower().strip(),
                        'search_text': f"{name or ''} {house_number}".lower().strip()
                    }

                return building_cache

            self.building_cache = await sync_to_async(load_sync)()
            logger.info(f"ObjectDetection: загружено {len(self.building_cache)} зданий")

        except Exception as e:
            logger.error(f"Ошибка загрузки зданий: {e}")
            self.building_cache = {}

    async def _load_service_objects(self):
        """Загрузка сервисных объектов"""
        try:
            def load_sync():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT so.service_object_id, so.building_id, so.unit_id,
                               u.unit_number
                        FROM service_objects so
                        LEFT JOIN units u ON so.unit_id = u.unit_id
                        WHERE so.is_active = TRUE
                    """)
                    results = cursor.fetchall()

                service_objects_cache = {}
                for row in results:
                    service_object_id, building_id, unit_id, unit_number = row

                    service_objects_cache[service_object_id] = {
                        'service_object_id': service_object_id,
                        'building_id': building_id,
                        'unit_id': unit_id,
                        'unit_number': unit_number.lower() if unit_number else ''
                    }

                return service_objects_cache

            self.service_objects_cache = await sync_to_async(load_sync)()
            logger.info(f"ObjectDetection: загружено {len(self.service_objects_cache)} сервисных объектов")

        except Exception as e:
            logger.error(f"Ошибка загрузки сервисных объектов: {e}")
            self.service_objects_cache = {}

    async def detect_service_object(self, message_text: str, previous_messages: List[str] = None) -> Dict:
        """
        Определение объекта обслуживания из текста сообщения

        Args:
            message_text: Текст сообщения пользователя
            previous_messages: Предыдущие сообщения в диалоге для контекста

        Returns:
            Dict: Результат определения объекта
        """
        try:
            logger.info(f"ObjectDetection: анализ текста '{message_text}'")

            if self.building_cache is None:
                await self._load_buildings()
            if self.service_objects_cache is None:
                await self._load_service_objects()

            # Объединяем все сообщения для анализа
            all_texts = [message_text]
            if previous_messages:
                all_texts.extend(previous_messages)
            combined_text = ' '.join(all_texts).lower()

            # Извлекаем информацию об адресе
            address_info = self._extract_address_info(combined_text)

            # Ищем подходящие здания
            matching_buildings = await self._find_matching_buildings(address_info)

            # Определяем тип проблемы (UNIT/COMMON)
            scope = self._determine_scope(combined_text)

            # Ищем конкретные объекты (квартиры)
            service_object = None
            if scope == "UNIT" and matching_buildings:
                service_object = await self._find_service_object(matching_buildings[0], address_info)

            result = {
                'status': 'success',
                'object_id': service_object['service_object_id'] if service_object else None,
                'building_id': matching_buildings[0]['building_id'] if matching_buildings else None,
                'scope': scope,
                'address_info': address_info,
                'matching_buildings': matching_buildings[:3],  # Топ-3 совпадения
                'service_object': service_object,
                'confidence': self._calculate_confidence(matching_buildings, address_info)
            }

            logger.info(f"ObjectDetection: найден объект {result['object_id']}, scope: {scope}")
            return result

        except Exception as e:
            logger.error(f"Ошибка в ObjectDetectionService: {e}")
            return {
                'status': 'error',
                'error': str(e),
                'object_id': None,
                'scope': 'UNKNOWN'
            }

    def _extract_address_info(self, text: str) -> Dict:
        """Извлечение информации об адресе из текста"""
        morph = self._get_morph()

        # Ищем номер дома/квартиры
        house_patterns = [
            r'дом\s+(\d+[а-яё]?)',
            r'д\s+(\d+[а-яё]?)',
            r'дом\s+№\s*(\d+[а-яё]?)',
            r'(\d+[а-яё]?)\s*дом',
            r'улица.*?(\d+[а-яё]?)',
            r'ул\s*.*?(\d+[а-яё]?)'
        ]

        apartment_patterns = [
            r'квартира\s*(\d+)',
            r'кв\s*(\d+)',
            r'кв\.\s*(\d+)',
            r'(\d+)\s*квартира',
            r'этаж\s*(\d+)',
            r'подъезд\s*(\d+)'
        ]

        address_info = {
            'house_number': None,
            'apartment_number': None,
            'street': None,
            'building_type': None,
            'location_indicators': []
        }

        # Ищем номер дома
        for pattern in house_patterns:
            match = re.search(pattern, text)
            if match:
                address_info['house_number'] = match.group(1).lower()
                break

        # Ищем номер квартиры
        for pattern in apartment_patterns:
            match = re.search(pattern, text)
            if match:
                address_info['apartment_number'] = match.group(1).lower()
                break

        # Определяем тип локации
        if any(word in text for word in ['квартира', 'кв', 'в квартире', 'домой', 'дома', 'в моем']):
            address_info['building_type'] = 'UNIT'
            address_info['location_indicators'].append('внутри помещения')
        elif any(word in text for word in ['подъезд', 'лифт', 'подвал', 'крыша', 'чердак', 'общее', 'общедом']):
            address_info['building_type'] = 'COMMON'
            address_info['location_indicators'].append('общественное пространство')

        return address_info

    async def _find_matching_buildings(self, address_info: Dict) -> List[Dict]:
        """Поиск подходящих зданий"""
        if not self.building_cache:
            return []

        matching_buildings = []

        # Если есть номер дома - ищем по нему
        if address_info['house_number']:
            house_number = address_info['house_number']

            for building_id, building_data in self.building_cache.items():
                score = 0.0

                # Точное совпадение номера дома
                if building_data['house_number'] == house_number:
                    score += 0.8

                # Совпадение по названию улицы
                if address_info.get('street'):
                    street_words = set(address_info['street'].split())
                    building_words = set(building_data['search_text'].split())
                    common_words = street_words.intersection(building_words)
                    if common_words:
                        score += 0.2 * (len(common_words) / max(len(street_words), 1))

                if score > 0.3:  # Порог совпадения
                    building_copy = building_data.copy()
                    building_copy['match_score'] = score
                    matching_buildings.append(building_copy)

        # Сортируем по релевантности
        matching_buildings.sort(key=lambda x: x['match_score'], reverse=True)
        return matching_buildings

    def _determine_scope(self, text: str) -> str:
        """Определение типа проблемы (UNIT/COMMON)"""
        # Признаки проблемы в конкретной квартире
        unit_indicators = [
            'квартира', 'кв', 'в моей квартире', 'у меня дома', 'в ванной', 'на кухне',
            'в комнате', 'в туалете', 'в моей', 'домой', 'в доме', 'моя'
        ]

        # Признаки общедомовой проблемы
        common_indicators = [
            'подъезд', 'лифт', 'общее', 'общедом', 'подвал', 'крыша', 'чердак',
            'фасад', 'входная', 'общая', 'сосед', 'на лестнице', 'на площадке'
        ]

        text_lower = text.lower()

        unit_score = sum(1 for indicator in unit_indicators if indicator in text_lower)
        common_score = sum(1 for indicator in common_indicators if indicator in text_lower)

        if unit_score > common_score:
            return "UNIT"
        elif common_score > 0:
            return "COMMON"
        else:
            # Если нет явных указателей, анализируем тип услуги
            if any(word in text_lower for word in ['квартира', 'домой']):
                return "UNIT"
            else:
                return "COMMON"  # По умолчанию считаем общим

    async def _find_service_object(self, building: Dict, address_info: Dict) -> Optional[Dict]:
        """Поиск конкретного сервисного объекта (квартиры)"""
        if not self.service_objects_cache:
            return None

        # Ищем объекты для этого здания
        building_objects = [
            obj for obj in self.service_objects_cache.values()
            if obj['building_id'] == building['building_id']
        ]

        if not building_objects:
            return None

        # Если есть номер квартиры - ищем по нему
        if address_info.get('apartment_number'):
            apartment_num = address_info['apartment_number']

            for obj in building_objects:
                if obj['unit_number'] == apartment_num:
                    return obj

        # Если номер квартиры не указан, возвращаем первый объект
        return building_objects[0]

    def _calculate_confidence(self, matching_buildings: List[Dict], address_info: Dict) -> float:
        """Расчет уверенности в определении объекта"""
        if not matching_buildings:
            return 0.0

        # Базовая уверенность от совпадения адреса
        base_confidence = matching_buildings[0]['match_score']

        # Бонус за указание номера квартиры
        if address_info.get('apartment_number'):
            base_confidence += 0.2

        # Бонус за указание типа локации
        if address_info.get('building_type'):
            base_confidence += 0.1

        return min(base_confidence, 1.0)