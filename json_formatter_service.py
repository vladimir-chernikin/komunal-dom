#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
JSONFormatterService - сервис формирования финального JSON ответа
Создает валидный JSON в соответствии с мини-ТЗ
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class JSONFormatterService:
    """Сервис формирования финального JSON ответа"""

    def __init__(self):
        logger.info("JSONFormatterService инициализирован")

    def create_final_json(self,
                         service_id: int,
                         confidence: float,
                         complaint_text: str,
                         object_id: Optional[int] = None,
                         scope: str = "COMMON",
                         dialog_history: List[Dict] = None) -> Dict:
        """
        Создание финального JSON ответа в соответствии с мини-ТЗ

        Args:
            service_id: ID найденной услуги из каталога услуг
            confidence: вероятность совпадения (0.0–1.0)
            complaint_text: полный текст обращения
            object_id: ID объекта обслуживания (null для общедомовых)
            scope: "UNIT" если квартира/помещение, "COMMON" если общедомовая проблема
            dialog_history: история диалога для формирования complaint_text

        Returns:
            Dict: Валидный JSON ответа
        """
        try:
            # Формируем complaint_text из истории диалога если не предоставлен
            if not complaint_text and dialog_history:
                complaint_text = self._build_complaint_text(dialog_history)

            # Нормализуем confidence в диапазон 0.0-1.0
            normalized_confidence = max(0.0, min(1.0, float(confidence)))

            # Валидация scope
            if scope not in ["UNIT", "COMMON"]:
                scope = "COMMON"

            # Формируем финальный JSON
            final_json = {
                "service_id": int(service_id),
                "confidence": round(normalized_confidence, 3),
                "complaint_text": complaint_text.strip() if complaint_text else "",
                "object_id": object_id,  # Может быть null для общедомовых проблем
                "scope": scope
            }

            logger.info(f"Создан финальный JSON: service_id={service_id}, confidence={normalized_confidence}, scope={scope}")
            return final_json

        except Exception as e:
            logger.error(f"Ошибка создании финального JSON: {e}")
            raise

    def _build_complaint_text(self, dialog_history: List[Dict]) -> str:
        """
        Формирование полного текста обращения из истории диалога

        Args:
            dialog_history: список сообщений с полями {text, sender, timestamp}

        Returns:
            str: Полный текст обращения в хронологическом порядке
        """
        try:
            if not dialog_history:
                return ""

            # Фильтруем и сортируем сообщения
            messages = []
            for msg in dialog_history:
                if msg.get('text') and msg.get('sender') == 'user':
                    messages.append({
                        'text': msg['text'].strip(),
                        'timestamp': msg.get('timestamp', datetime.now())
                    })

            # Сортируем по времени
            messages.sort(key=lambda x: x['timestamp'])

            # Склеиваем тексты
            complaint_parts = []
            for msg in messages:
                text = msg['text']
                # Убираем повторы и пустые фразы
                if text and text.lower() not in ['да', 'нет', 'ок', 'хорошо']:
                    complaint_parts.append(text)

            return '. '.join(complaint_parts) + '.' if complaint_parts else ""

        except Exception as e:
            logger.error(f"Ошибка формировании текста обращения: {e}")
            return ""

    def format_for_telegram(self, final_json: Dict) -> str:
        """
        Форматирование JSON для отправки в Telegram
        Возвращает строго валидный JSON как строку

        Args:
            final_json: Словарь с финальными данными

        Returns:
            str: JSON строка для отправки
        """
        try:
            # Преобразуем в JSON строку
            json_str = json.dumps(final_json, ensure_ascii=False, separators=(',', ':'))

            logger.info(f"Сформирован JSON для Telegram: {json_str}")
            return json_str

        except Exception as e:
            logger.error(f"Ошибка форматировании JSON для Telegram: {e}")
            raise

    def validate_final_json(self, final_json: Dict) -> bool:
        """
        Валидация финального JSON в соответствии с мини-ТЗ

        Args:
            final_json: Словарь для валидации

        Returns:
            bool: True если валидный
        """
        try:
            # Проверяем обязательные поля
            required_fields = ["service_id", "confidence", "complaint_text", "object_id", "scope"]
            for field in required_fields:
                if field not in final_json:
                    logger.error(f"Отсутствует обязательное поле: {field}")
                    return False

            # Проверяем типы данных
            if not isinstance(final_json["service_id"], int):
                logger.error("service_id должен быть int")
                return False

            if not isinstance(final_json["confidence"], (int, float)):
                logger.error("confidence должен быть числом")
                return False

            if not isinstance(final_json["complaint_text"], str):
                logger.error("complaint_text должен быть строкой")
                return False

            if final_json["object_id"] is not None and not isinstance(final_json["object_id"], int):
                logger.error("object_id должен быть int или null")
                return False

            if final_json["scope"] not in ["UNIT", "COMMON"]:
                logger.error("scope должен быть 'UNIT' или 'COMMON'")
                return False

            # Проверяем диапазоны
            if not (0.0 <= final_json["confidence"] <= 1.0):
                logger.error("confidence должен быть в диапазоне 0.0-1.0")
                return False

            logger.info("JSON прошел валидацию")
            return True

        except Exception as e:
            logger.error(f"Ошибка валидации JSON: {e}")
            return False

    def create_error_json(self, error_message: str) -> Dict:
        """
        Создание JSON ответа с ошибкой (не отправляется пользователю)

        Args:
            error_message: Текст ошибки

        Returns:
            Dict: JSON с информацией об ошибке
        """
        return {
            "error": True,
            "error_message": error_message,
            "timestamp": datetime.now().isoformat()
        }

    def extract_confirmation_buttons(self, final_json: Dict) -> List[List[Dict]]:
        """
        Создание кнопок подтверждения для JSON ответа

        Args:
            final_json: Финальный JSON данные

        Returns:
            List[List[Dict]]: Кнопки для Telegram
        """
        try:
            service_name = self._get_service_name_by_id(final_json["service_id"])

            buttons = [
                [
                    {"text": "✅ Подтвердить", "callback_data": f"confirm_{final_json['service_id']}"},
                    {"text": "❌ Изменить", "callback_data": f"edit_{final_json['service_id']}"}
                ]
            ]

            # Добавляем кнопку с деталями если есть object_id
            if final_json.get("object_id"):
                buttons.append([
                    {"text": "📍 Детали адреса", "callback_data": f"details_{final_json['object_id']}"}
                ])

            return buttons

        except Exception as e:
            logger.error(f"Ошибка создании кнопок: {e}")
            return []

    def _get_service_name_by_id(self, service_id: int) -> str:
        """
        Получение названия услуги по ID (заглушка)

        Args:
            service_id: ID услуги

        Returns:
            str: Название услуги
        """
        # TODO: Реализовать получение из БД
        service_names = {
            1: "Устранение течи в квартире",
            2: "Устранение течи в подвале",
            3: "Засор канализации",
            4: "Отопление не работает",
            5: "Сломался лифт",
            6: "Поверка счетчиков",
            7: "Вызов сантехника"
        }
        return service_names.get(service_id, f"Услуга #{service_id}")