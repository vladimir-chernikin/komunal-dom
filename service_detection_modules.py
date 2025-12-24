#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модули для системы обнаружения услуг Telegram бота УК "Аспект"
Включает: Anti-Spam Filter, Precision Funnel (Levels 1-3), Address Extraction
"""

import re
import json
import uuid
import logging
from typing import Dict, List, Tuple, Optional, Any
from datetime import datetime
from django.db import connection
import pymorphy2

# Настройка логирования
logger = logging.getLogger(__name__)

# Попытка импортировать дополнительные библиотеки
try:
    from fuzzywuzzy import fuzz, process
    FUZZY_AVAILABLE = True
except ImportError:
    FUZZY_AVAILABLE = False
    logger.warning("fuzzywuzzy не установлен, будет использоваться difflib")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("openai не установлен, LLM функции будут недоступны")

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logger.warning("google-generativeai не установлен, Gemini будет недоступен")


class AntiSpamFilter:
    """Фильтр для определения целевых обращений с 4 уровнями проверки"""

    SPAM_KEYWORDS = [
        'купи', 'заработай', 'инвестиции', 'кредит', 'займ',
        'порно', 'секс', 'казино', 'букмекер', 'ставки',
        'трейдинг', 'форекс', 'бинарные опционы', 'криптовалюта',
        'млм', 'сетевой маркетинг', 'бизнес-предложение', 'наживо'
    ]

    # НОВЫЕ: Списки ругательств и неконструктивных паттернов
    PROFANITY_WORDS = [
        'хуй', 'пизд', 'бляд', 'еба', 'блять', 'говно',
        'жопа', 'хер', 'падл', 'урод', 'сволоч', 'дебил',
        'дур', 'туп', 'лох', 'придур', 'козел', 'ебать',
        'заёб', 'засра', 'полнен', 'хуить', 'ебос', 'пиздеть',
        'козлы', 'уроды', 'идиоты'  # Добавляем множественные формы
    ]

    NON_CONSTRUCTIVE_PATTERNS = [
        # Оскорбления и нецензурная критика
        r'(?:вы|ты)\s+(?:уроды|козлы|идиоты|дебилы|жеребцы|тупицы|долбоебы)',
        r'(?:это\s+)?(?:пиздеж|кино|театр|херня|фигня|дичь)',
        r'(?:мне\s+|мною\s+)?(?:плевать|пофиг|всё\s+равно|без\s+разницы)',
        r'(?:на\s+)?(?:хуй|фиг|похуй|заебала|достала)',
        r'(?:сложил|заёб|достал|пиздит|наплевал|обманули)',

        # Неконструктивная критика
        r'это\s+(?:полный\s+)?(?:отстой|бред|дурь|чушь|фуфло)',
        r'(?:ужасно|плохо|дерьмо|параша)\s*',
        r'(?:никогда\s+)?(?:не\s+работает|не\s+поможет|не\s+решат)',
        r'(?:бесполезно|бесполезные|никчемные)',

        # Угрозы и давление
        r'(?:пожалуюсь|напишу\s+жалобу|суд\s+будет)',
        r'(?:уволить|заменить|убрать)\s+(?:всех|вас)',
        r'(?:закон|права|прокуратура)\s*',

        # Эмоциональные всплески без конструктива
        r'(?:ужас|катастрофа|кризис|конец)',
        r'(?:как\s+так|почему\s+так|не\s+может\s+быть)',
        r'(?:наконец\s+то|уже\s+надоело|всё\s+одно\s+и\s+то\s+же)',

        # Требования без объяснения
        r'(?:срочно\s+)?(?:нужно\s+сделать|придите|решите)',
        r'(?:немедленно|быстрее|побыстрее|сейчас\s+же)',
        r'^(?:требую|хочу|нужно|пусть)',

        # Пассивная агрессия
        r'(?:конечно|естественно|разумеется)\s*,\s*но\s*',
        r'(?:делайте\s+что\s+хотите|вам\s+решать|как\s+знаете)',
        r'(?:видимо|наверное|похоже)\s*',

        # Обесценивание
        r'(?:это\s+не\s+(?:важно|срочно|нужно))',
        r'(?:какая\s+разница|что\s+вы\s+будете\s+делать)',
        r'(?:никто\s+не\s+поможет|все\s+равно\s+ничего)',

        # Манипуляции
        r'(?:я\s+платил|я\s+заказывал|я\s+вас\s+нанял)',
        r'(?:вы\s+обязаны|должны|за\s*это\s*платят)',
        r'(?:я\s+ваш\s+клиент|я\s+тут\s+хозяин)',
    ]

    MIN_MESSAGE_LENGTH = 2  # минимум слов
    MAX_REPEATED_CHARS = 3  # максимум повторяющихся символов подряд

    def __init__(self):
        try:
            self.morph = pymorphy2.MorphAnalyzer()
            self.use_morph = True
        except Exception as e:
            logger.warning(f"pymorphy2 не доступен: {e}")
            self.morph = None
            self.use_morph = False

    def check_message(self, message_text: str) -> Dict:
        """
        Проверить сообщение на спам, ругань, неконструктивность, расплывчатость.

        Возвращает Dict с результатом проверки по 4 уровням.
        """
        try:
            # Сначала проверяем на ругательства (самый высокий приоритет)
            profanity_check = self._check_profanity(message_text)
            if profanity_check['found']:
                return {
                    'is_spam': True,
                    'reason': f'Обнаружено нецензурное слово: {profanity_check["word"]}',
                    'confidence': profanity_check['severity'],
                    'category': 'PROFANITY',
                    'action': 'WARN_AND_RETRY',  # Предупредить и попросить переформулировать
                    'details': profanity_check  # Добавляем детализацию
                }

            # Проверяем на неконструктивность
            non_constructive = self._check_non_constructive(message_text)
            if non_constructive['found']:
                return {
                    'is_spam': True,
                    'reason': 'Сообщение содержит неконструктивные элементы',
                    'confidence': non_constructive['severity'],
                    'category': 'NON_CONSTRUCTIVE',
                    'action': 'WARN_AND_RETRY',  # То же - предупредить
                    'details': non_constructive  # Добавляем детализацию
                }

            # УРОВЕНЬ 4: Расплывчатость (проверяем до BasicSpam!)
            if self._is_too_vague(message_text):
                return {
                    'is_spam': False,  # ❗ Не спам, но непонятно
                    'reason': 'Сообщение слишком расплывчато',
                    'confidence': 0.6,
                    'category': 'VAGUE',
                    'action': 'ASK_FOR_CLARIFICATION'  # Попросить конкретики
                }

            # УРОВЕНЬ 1: Базовый спам (проверяем после VAGUE)
            if self._check_basic_spam(message_text):
                return {
                    'is_spam': True,
                    'reason': 'Обнаружен спам',
                    'confidence': 0.95,
                    'category': 'SPAM',
                    'action': 'REJECT'  # Отклонить
                }

            # ВСЕ OK
            return {
                'is_spam': False,
                'reason': 'OK',
                'confidence': 1.0,
                'category': 'OK',
                'action': 'PROCESS'  # Обработать нормально
            }

        except Exception as e:
            logger.error(f"Error checking message '{message_text}': {e}")
            return {
                'is_spam': False,
                'reason': 'Ошибка проверки',
                'confidence': 0.0,
                'category': 'ERROR',
                'action': 'PROCESS'
            }

    def _check_basic_spam(self, message_text: str) -> bool:
        """
        Проверить базовый спам (keywords, URL, повторения).

        Args:
            message_text: Текст сообщения

        Returns:
            bool: True если спам обнаружен
        """
        try:
            # 1. Проверяем spam keywords
            text_lower = message_text.lower()
            for keyword in self.SPAM_KEYWORDS:
                if keyword in text_lower:
                    logger.info(f"Spam keyword detected: {keyword}")
                    return True

            # 2. Проверяем минимальную длину
            words = message_text.split()
            if len(words) < self.MIN_MESSAGE_LENGTH:
                logger.info(f"Message too short: {len(words)} words")
                return True

            # 3. Проверяем URL (часто в спаме)
            if re.search(r'http[s]?://', message_text):
                logger.info("URL detected in message")
                return True

            # 4. Проверяем повторяющиеся символы (признак спама)
            if re.search(r'(.)\1{' + str(self.MAX_REPEATED_CHARS) + r',}', message_text):
                logger.info("Repeated characters detected")
                return True

            # 5. Проверяем на много восклицательных знаков
            if message_text.count('!') > 3:
                logger.info("Too many exclamation marks")
                return True

            # 6. Проверяем на заглавные буквы (кричащий текст)
            if len(message_text) > 10:
                upper_ratio = sum(1 for c in message_text if c.isupper()) / len(message_text)
                if upper_ratio > 0.7:
                    logger.info("Too many uppercase letters")
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking basic spam: {e}")
            return False

    def _check_profanity(self, text: str) -> Dict:
        """
        Проверить наличие ругательств в тексте.

        Args:
            text: Текст сообщения

        Returns:
            Dict: {'found': bool, 'word': str, 'count': int, 'severity': float}
        """
        try:
            text_lower = text.lower()

            for word in self.PROFANITY_WORDS:
                if word in text_lower:
                    count = text_lower.count(word)
                    severity = min(0.95, 0.7 + (count * 0.1))  # увеличивается с количеством ругательств

                    logger.warning(f"Profanity detected: '{word}' (count: {count}, severity: {severity:.2f})")

                    return {
                        'found': True,
                        'word': word,
                        'count': count,
                        'severity': severity
                    }

            return {'found': False}

        except Exception as e:
            logger.error(f"Error checking profanity: {e}")
            return {'found': False}

    def _check_non_constructive(self, text: str) -> Dict:
        """
        Проверить неконструктивные сообщения.

        Args:
            text: Текст сообщения

        Returns:
            Dict: {'found': bool, 'pattern': str, 'severity': float}
        """
        try:
            text_lower = text.lower()
            words = text_lower.split()

            # Улучшенная система определения严重ности (severity)
            severity = 0.5  # Базовая严重ность
            matched_patterns = []

            # Проверяем каждый паттерн
            for pattern in self.NON_CONSTRUCTIVE_PATTERNS:
                match = re.search(pattern, text_lower)
                if match:
                    matched_patterns.append(pattern)

                    # Увеличиваем серьезность в зависимости от типа паттерна
                    if any(word in pattern for word in ['уроды', 'козлы', 'идиоты', 'дебилы']):
                        severity = max(severity, 0.9)  # Прямые оскорбления
                    elif any(word in pattern for word in ['пожалуюсь', 'суд', 'прокуратура']):
                        severity = max(severity, 0.85)  # Угрозы
                    elif any(word in pattern for word in ['пизд', 'еб', 'хуй']):
                        severity = max(severity, 0.8)  # Мат
                    elif any(word in pattern for word in ['требую', 'хочу', 'немедленно']):
                        severity = max(severity, 0.7)  # Требования
                    else:
                        severity = max(severity, 0.6)  # Общая неконструктивность

            # Дополнительные эвристики для повышения серьезности
            if len(words) <= 3 and matched_patterns:
                severity = min(severity + 0.2, 1.0)  # Короткие агрессивные сообщения

            # Много капслока
            if len(text) > 5 and sum(1 for c in text if c.isupper()) / len(text) > 0.5:
                severity = min(severity + 0.15, 1.0)

            # Много восклицательных знаков
            if text.count('!') > 2:
                severity = min(severity + 0.1, 1.0)

            # Если нашли паттерны
            if matched_patterns:
                logger.warning(f"Non-constructive pattern detected: {matched_patterns[0]} (severity: {severity:.2f})")

                return {
                    'found': True,
                    'pattern': matched_patterns[0],  # Первый найденный паттерн
                    'severity': severity,
                    'patterns_count': len(matched_patterns)  # Для информации
                }

            return {'found': False}

        except Exception as e:
            logger.error(f"Error checking non-constructive: {e}")
            return {'found': False}

    def _is_too_vague(self, text: str) -> bool:
        """
        Проверить не слишком ли расплывчатое сообщение.

        Args:
            text: Текст сообщения

        Returns:
            bool: True если сообщение расплывчатое
        """
        try:
            # Приводим к нижнему регистру для анализа
            text_lower = text.strip().lower()
            words = text_lower.split()

            # 1. Односложные сообщения без деталей
            single_word_patterns = [
                r'^(?:помогите|помоги|помог|привет|здравствуй|спасибо|благодарю|добрый|вечер|день|утро)$',
                r'^(?:хай|ку|прив)$',  # Сокращения
                r'^(?:алло|да|нет|да?$)',  # Короткие ответы
                r'^(?:помощь|нужна|нужен|помощью)$',  # Просьбы помощи без деталей
            ]

            # 2. Слишком короткие сообщения (1 слово)
            if len(words) == 1:
                # Проверяем не является ли это конкретной проблемой
                concrete_words = [
                    'протекает', 'течет', 'капает', 'ломается', 'не', 'работает',
                    'засор', 'перебой', 'отсутствует', 'пропал', 'сломался',
                    'горячая', 'холодная', 'батарея', 'кран', 'свет', 'газ',
                    'счетчик', 'квитанция', 'оплата', 'тариф', 'долг'
                ]

                # Если слово не входит в список конкретных - считаем расплывчатым
                if not any(word in text_lower for word in concrete_words):
                    logger.info(f"Single vague word: {text_lower}")
                    return True

            # 3. Паттерны расплывчатых фраз
            vague_patterns = [
                r'(?:что[-\s]то|что[-\s]то\s+там)',  # "что-то там"
                r'(?:не\s+знаю|не\s+помню|не\s+понимаю)',  # "не знаю"
                r'^\s*(?:проблем|непорядок|не\s+так)\s*$',  # Неопределенно (только эти слова)
                r'^(?:вопрос\s+есть|есть\s+вопрос)$',  # "есть вопрос" без деталей
                r'^(?:что\s+делать|как\s+быть)$',  # "что делать" без контекста
                r'^(?:нужно\s+помощь|требуется\s+помощь)$',  # Просьбы помощи без деталей
                r'^(?:посмотрите|проверьте)$',  # Просьбы проверки без деталей
                r'^[!?]{1,3}$',  # Только знаки препинания
                r'^\s*$',  # Пустое сообщение
            ]

            # Проверяем паттерны
            for pattern in vague_patterns:
                if re.search(pattern, text_lower):
                    logger.info(f"Vague pattern detected: {text_lower[:30]}...")
                    return True

            # 4. Вопросы без конкретики (только вопросительные слова)
            if len(words) <= 3 and any(word in text_lower for word in ['кто', 'что', 'где', 'когда', 'как', 'почему', 'зачем']):
                concrete_indicators = [
                    'сломалось', 'протекает', 'не', 'работает', 'засорился',
                    'отключили', 'горячая', 'холодная', 'свет', 'газ', 'вода'
                ]
                if not any(indicator in text_lower for indicator in concrete_indicators):
                    logger.info(f"Vague question detected: {text_lower}")
                    return True

            return False

        except Exception as e:
            logger.error(f"Error checking vagueness: {e}")
            return False


class PrecisionFunnelLevel1:
    """Быстрая фильтрация на уровне Python"""

    def __init__(self):
        try:
            self.morph = pymorphy2.MorphAnalyzer()
            self.use_morph = True
        except Exception as e:
            logger.warning(f"pymorphy2 не доступен: {e}")
            self.morph = None
            self.use_morph = False

    def normalize_text(self, text: str) -> str:
        """Нормализация входного текста"""
        # 1. Привести к нижнему регистру
        text = text.lower()

        # 2. Убрать лишние пробелы и пунктуацию
        text = re.sub(r'\s+', ' ', text).strip()
        text = re.sub(r'[,.!?;:]', '', text)

        # 3. Заменить аббревиатуры на полные формы
        abbreviations = {
            r'\bул\b': 'улица',
            r'\bпр\b': 'проспект',
            r'\bпр-т\b': 'проспект',
            r'\bпер\b': 'переулок',
            r'\bб-р\b': 'бульвар',
            r'\bм-н\b': 'микрорайон',
            r'\bгвс\b': 'горячая вода',
            r'\bхвс\b': 'холодная вода',
            r'\bуло\b': 'управляющая компания',
            r'\bук\b': 'управляющая компания',
        }
        for abbrev, full in abbreviations.items():
            text = re.sub(abbrev, full, text)

        return text

    def lemmatize_tokens(self, text: str) -> List[str]:
        """Лемматизация текста"""
        tokens = text.split()
        lemmas = []

        for token in tokens:
            if self.use_morph and self.morph:
                # Используем pymorphy2 для лемматизации
                parsed = self.morph.parse(token)
                if parsed:
                    lemma = parsed[0].normal_form
                    if len(lemma) > 2:  # фильтруем короткие слова
                        lemmas.append(lemma)
            else:
                # Если pymorphy2 недоступен, используем простую нормализацию
                lemma = token.lower().strip('.,!?;:')
                if len(lemma) > 2:
                    lemmas.append(lemma)

        return lemmas

    def get_exact_tag_matches(self, lemmas: List[str]) -> List[Tuple[int, float]]:
        """Поиск точных совпадений по тегам из БД"""

        try:
            logger.info(f"Поиск точных совпадений по леммам: {lemmas[:10]}...")

            # Ищем точные совпадения в БД через Django connection
            from django.db import connection

            with connection.cursor() as cursor:
                # Получаем все активные теги из БД с их весами
                cursor.execute("""
                    SELECT tag_id, tag_name, weight_coefficient
                    FROM ref_tags
                    WHERE is_active = TRUE
                """)
                tags = cursor.fetchall()

                # Строим словарь: tag_lemma -> (tag_id, weight)
                tag_dict = {}
                for tag_id, tag_name, weight in tags:
                    if tag_name:
                        if self.use_morph and self.morph:
                            tag_lemma = self.morph.parse(tag_name)[0].normal_form
                        else:
                            tag_lemma = tag_name.lower()
                        tag_dict[tag_lemma] = (tag_id, weight)

                # Ищем совпадения в леммах
                matched_tags = []
                tag_scores = {}

                for lemma in lemmas:
                    if lemma in tag_dict:
                        tag_id, weight = tag_dict[lemma]
                        matched_tags.append(tag_id)
                        tag_scores[tag_id] = weight

                if not matched_tags:
                    logger.info("Точных совпадений по тегам не найдено")
                    return []

                # Получаем услуги, связанные с найденными тегами
                placeholders = ','.join(['%s'] * len(matched_tags))
                cursor.execute(f"""
                    SELECT DISTINCT sc.service_id,
                           SUM(st.tag_weight * COALESCE(rt.weight_coefficient, 1.0)) as total_score
                    FROM service_tags st
                    JOIN services_catalog sc ON st.service_id = sc.service_id
                    JOIN ref_tags rt ON st.tag_id = rt.tag_id
                    WHERE st.tag_id IN ({placeholders})
                      AND sc.is_active = TRUE
                    GROUP BY sc.service_id
                    ORDER BY total_score DESC
                    LIMIT 5
                """, matched_tags)

                results = cursor.fetchall()
                service_candidates = [(service_id, float(score)) for service_id, score in results]

                logger.info(f"Найдено услуг по тегам: {service_candidates}")
                return service_candidates

        except Exception as e:
            logger.error(f"Ошибка в get_exact_tag_matches: {e}")
            return []

    def apply_category_filters(self, candidates: List[Tuple[int, float]], text: str) -> List[Tuple[int, float]]:
        """Применяем категорийные фильтры для сужения выборки"""

        emergency_keywords = [
            'протечка', 'прорыв', 'течет', 'затопление', 'газ',
            'пожар', 'нет света', 'нет отопления', 'авария', 'запах газа'
        ]
        request_keywords = [
            'ремонт', 'замена', 'установка', 'монтаж', 'справка',
            'консультация', 'информация', 'документ', 'справка'
        ]

        is_emergency = any(kw in text for kw in emergency_keywords)
        is_request = any(kw in text for kw in request_keywords)

        filtered = []
        for service_id, score in candidates:
            try:
                from django.db import connection
                with connection.cursor() as cursor:
                    # Получаем тип и вид услуги
                    cursor.execute("""
                        SELECT sc.type_id, sc.kind_id, rc.category_code
                        FROM services_catalog sc
                        LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                        WHERE sc.service_id = %s
                    """, [service_id])
                    result = cursor.fetchone()

                    if result:
                        type_id, kind_id, category_code = result

                        # Применяем фильтр
                        if is_emergency and category_code and 'EMERGENCY' not in category_code:
                            continue
                        elif is_request and category_code and 'REQUEST' not in category_code:
                            continue

                        # Увеличиваем score для экстренных случаев
                        if is_emergency:
                            score *= 1.2
                        elif is_request:
                            score *= 1.1

                        filtered.append((service_id, min(score, 1.0)))
                    else:
                        # Если не нашли в БД, просто добавляем кандидата
                        filtered.append((service_id, score))

            except Exception as e:
                logger.error(f"Ошибка в apply_category_filters: {e}")
                filtered.append((service_id, score))

        return sorted(filtered, key=lambda x: x[1], reverse=True)[:5]

    def run(self, message_text: str) -> Dict:
        """Основной метод Level 1"""
        # 1. Нормализуем текст
        normalized = self.normalize_text(message_text)

        # 2. Лемматизируем
        lemmas = self.lemmatize_tokens(normalized)

        # 3. Ищем точные совпадения по тегам
        candidates = self.get_exact_tag_matches(lemmas)

        if not candidates:
            return {
                'level': 1,
                'status': 'NO_MATCH',
                'candidates': [],
                'confidence': 0.0,
                'decision': 'ESCALATE_TO_LEVEL_2'
            }

        # 4. Применяем категорийные фильтры
        filtered = self.apply_category_filters(candidates, normalized)

        if not filtered:
            return {
                'level': 1,
                'status': 'NO_MATCH',
                'candidates': [],
                'confidence': 0.0,
                'decision': 'ESCALATE_TO_LEVEL_2'
            }

        # 5. Если первый кандидат имеет high confidence, возвращаем его
        if filtered[0][1] > 0.85:
            return {
                'level': 1,
                'status': 'HIGH_CONFIDENCE_MATCH',
                'service_id': filtered[0][0],
                'confidence': float(filtered[0][1]),
                'candidates': [(s_id, float(score)) for s_id, score in filtered],
                'decision': 'PROCEED_TO_ADDRESS'
            }

        # Иначе передаем кандидатов на уровень 2 или 3
        return {
            'level': 1,
            'status': 'PARTIAL_MATCH',
            'candidates': [(s_id, float(score)) for s_id, score in filtered],
            'confidence': filtered[0][1] if filtered else 0.0,
            'decision': 'ESCALATE_TO_LEVEL_2'
        }


class PrecisionFunnelLevel2:
    """Векторный поиск и нечеткое совпадение (упрощенная версия)"""

    def __init__(self):
        pass

    def fuzzy_match_scenario_names(self, message_text: str, candidates: List[Tuple[int, float]]) -> List[Tuple[int, float]]:
        """Нечеткое совпадение по названиям сценариев услуг"""

        try:
            with connection.cursor() as cursor:
                # Получаем названия сценариев для кандидатов
                placeholders = ','.join(['%s'] * len(candidates))
                cursor.execute(f"""
                    SELECT service_id, scenario_name
                    FROM services_catalog
                    WHERE service_id IN ({placeholders})
                """, [service_id for service_id, _ in candidates])

                scenarios = cursor.fetchall()

                # Вычисляем нечеткое сходство
                fuzzy_scores = []
                for service_id, scenario_name in scenarios:
                    if FUZZY_AVAILABLE:
                        # Используем fuzzywuzzy
                        ratio = fuzz.ratio(message_text.lower(), scenario_name.lower()) / 100.0
                    else:
                        # Fallback на difflib
                        from difflib import SequenceMatcher
                        ratio = SequenceMatcher(
                            None,
                            message_text.lower(),
                            scenario_name.lower()
                        ).ratio()

                    fuzzy_scores.append((service_id, ratio))

                return fuzzy_scores
        except Exception as e:
            logger.error(f"Ошибка в fuzzy_match_scenario_names: {e}")
            return []

    def run(self, message_text: str, level1_candidates: List[Tuple[int, float]]) -> Dict:
        """Level 2: Объединяем fuzzy поиск"""

        if not level1_candidates:
            return {
                'level': 2,
                'status': 'NO_CANDIDATES',
                'decision': 'ESCALATE_TO_LEVEL_3'
            }

        # Добавляем fuzzy matching по названиям
        fuzzy_scores = self.fuzzy_match_scenario_names(message_text, level1_candidates)

        # Объединяем результаты
        final_candidates = []
        for service_id, level1_score in level1_candidates:
            fuzzy_score = next(
                (score for s_id, score in fuzzy_scores if s_id == service_id),
                0.0
            )
            # Комбинируем score'ы
            final_score = level1_score * 0.6 + fuzzy_score * 0.4
            final_candidates.append((service_id, final_score))

        # Сортируем по score и берем top-3
        final_candidates.sort(key=lambda x: x[1], reverse=True)
        final_candidates = final_candidates[:3]

        # Если best candidate имеет хороший score, берем его
        if final_candidates and final_candidates[0][1] > 0.70:
            return {
                'level': 2,
                'status': 'GOOD_MATCH',
                'service_id': final_candidates[0][0],
                'confidence': float(final_candidates[0][1]),
                'candidates': [(s_id, float(score)) for s_id, score in final_candidates],
                'decision': 'PROCEED_TO_ADDRESS'
            }

        # Иначе → Level 3
        return {
            'level': 2,
            'status': 'AMBIGUOUS',
            'candidates': [(s_id, float(score)) for s_id, score in final_candidates],
            'confidence': final_candidates[0][1] if final_candidates else 0.0,
            'decision': 'ESCALATE_TO_LEVEL_3_OR_CLARIFY'
        }


class PrecisionFunnelLevel3:
    """Поиск с использованием LLM (Last Resort)"""

    def __init__(self):
        self.yandex_api_key = None
        self.yandex_folder_id = None

        # Пытаемся получить ключи из настроек
        try:
            from decouple import config
            self.yandex_api_key = config('YANDEX_API_KEY', default=None)
            self.yandex_folder_id = config('YANDEX_FOLDER_ID', default=None)
        except:
            pass

    def build_service_catalog_context(self) -> str:
        """Собираем контекст всех услуг для LLM"""
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT scenario_id, scenario_name, description_for_search
                    FROM services_catalog
                    WHERE is_active = TRUE
                    ORDER BY scenario_id
                    LIMIT 20  -- Ограничиваем для экономии токенов
                """)
                services = cursor.fetchall()

                if not services:
                    return "Нет доступных услуг в каталоге."

                context = "Доступные услуги:\n"
                for scenario_id, scenario_name, description in services:
                    context += f"- {scenario_id}: {scenario_name}\n"
                    if description:
                        context += f"  Описание: {description}\n"

                return context
        except Exception as e:
            logger.error(f"Ошибка в build_service_catalog_context: {e}")
            return "Ошибка при загрузке каталога услуг."

    def call_llm(self, message_text: str, candidates: List[Tuple[int, float]]) -> Dict:
        """Вызываем LLM для определения услуги"""

        # Собираем контекст услуг
        services_context = self.build_service_catalog_context()

        # Формируем промпт
        prompt = f"""Ты - профессиональный диспетчер ЖКХ. У тебя есть список услуг управляющей компании.

Описание проблемы пользователя: "{message_text}"

{services_context}

Выбери наиболее подходящую услугу. Ответь в формате:
СЦЕНАРИЙ: [XXX-YYY-ZZZ]
НАЗВАНИЕ: [название услуги]
УВЕРЕННОСТЬ: [0.0-1.0]
ПРИЧИНА: [краткое обоснование]

Если ни одна услуга не подходит, ответь:
СЦЕНАРИЙ: NONE
ПРИЧИНА: [описание почему не подходит]"""

        # Пробуем сначала YandexGPT
        if self.yandex_api_key and self.yandex_folder_id:
            result = self._call_yandexgpt(prompt)
            if result:
                return result

        # Если Yandex не сработал, пробуем другие LLM
        if OPENAI_AVAILABLE:
            result = self._call_openai(prompt)
            if result:
                return result

        # Если ничего не сработало
        return {
            'level': 3,
            'status': 'LLM_ERROR',
            'error': 'Все LLM недоступны',
            'decision': 'ASK_CLARIFICATION'
        }

    def _call_yandexgpt(self, prompt: str) -> Optional[Dict]:
        """Вызов YandexGPT API"""
        try:
            import requests

            url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
            headers = {
                "Authorization": f"Api-Key {self.yandex_api_key}",
                "Content-Type": "application/json"
            }

            data = {
                "modelUri": f"gpt://{self.yandex_folder_id}/yandexgpt-lite",
                "completionOptions": {
                    "stream": False,
                    "temperature": 0.3,
                    "maxTokens": 500
                },
                "messages": [
                    {
                        "role": "user",
                        "text": prompt
                    }
                ]
            }

            response = requests.post(url, headers=headers, json=data, timeout=10)

            if response.status_code == 200:
                result = response.json()
                text = result['result']['alternatives'][0]['message']['text']
                return self._parse_llm_response(text)
            else:
                logger.error(f"YandexGPT API error: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Ошибка вызова YandexGPT: {e}")
            return None

    def _call_openai(self, prompt: str) -> Optional[Dict]:
        """Вызов OpenAI API"""
        try:
            if not OPENAI_AVAILABLE:
                return None

            client = openai.OpenAI()
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "Ты - профессиональный диспетчер ЖКХ. Отвечай точно по заданной структуре."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=500
            )

            text = response.choices[0].message.content
            return self._parse_llm_response(text)
        except Exception as e:
            logger.error(f"Ошибка вызова OpenAI: {e}")
            return None

    def _parse_llm_response(self, text: str) -> Dict:
        """Парсим ответ от LLM"""
        try:
            lines = text.strip().split('\n')
            result = {}

            for line in lines:
                if ':' in line:
                    key, value = line.split(':', 1)
                    result[key.strip()] = value.strip()

            if result.get('СЦЕНАРИЙ') == 'NONE':
                return {
                    'level': 3,
                    'status': 'NO_SERVICE_FOUND',
                    'reason': result.get('ПРИЧИНА', 'Услуга не найдена'),
                    'decision': 'ASK_CLARIFICATION'
                }

            # Ищем service_id по scenario_id
            scenario_id = result.get('СЦЕНАРИЙ', '')
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
                        SELECT service_id FROM services_catalog
                        WHERE scenario_id = %s AND is_active = TRUE
                    """, [scenario_id])
                    service_result = cursor.fetchone()

                    if service_result:
                        service_id = service_result[0]
                        confidence = float(result.get('УВЕРЕННОСТЬ', 0.5))

                        return {
                            'level': 3,
                            'status': 'LLM_MATCH',
                            'service_id': service_id,
                            'scenario_id': scenario_id,
                            'scenario_name': result.get('НАЗВАНИЕ', ''),
                            'confidence': confidence,
                            'reason': result.get('ПРИЧИНА', ''),
                            'decision': 'PROCEED_TO_ADDRESS'
                        }
            except Exception as e:
                logger.error(f"Ошибка поиска service_id: {e}")

            return {
                'level': 3,
                'status': 'LLM_ERROR',
                'error': f'Не найдена услуга для сценария {scenario_id}',
                'decision': 'ASK_CLARIFICATION'
            }
        except Exception as e:
            logger.error(f"Ошибка парсинга ответа LLM: {e}")
            return {
                'level': 3,
                'status': 'LLM_ERROR',
                'error': f'Ошибка парсинга: {str(e)}',
                'decision': 'ASK_CLARIFICATION'
            }

    def run(self, message_text: str, level2_result: Dict) -> Dict:
        """Level 3: используем LLM"""
        candidates = level2_result.get('candidates', [])
        return self.call_llm(message_text, candidates)


class AddressExtractor:
    """Извлечение и валидация адреса"""

    def __init__(self):
        try:
            self.morph = pymorphy2.MorphAnalyzer()
            self.use_morph = True
        except Exception as e:
            logger.warning(f"pymorphy2 не доступен: {e}")
            self.morph = None
            self.use_morph = False

    def extract_address_components(self, text: str, context_memory: Dict = None) -> Dict:
        """
        Извлечь компоненты адреса из текста И объединить с памятью.

        КЛЮЧЕВОЙ МЕТОД для восстановления адреса из кусков!

        Args:
            text: Текущее сообщение
            context_memory: Dict с extracted_entities из DialogMemoryManager
                       {street, house_number, apartment_number, entrance}

        Returns:
            Dict с адресными компонентами + confidence
        """

        # ШАГ 1: Парсить текущее сообщение
        current_components = self._parse_address_text(text)

        # ШАГ 2: Объединить с памятью
        if context_memory:
            result = self._merge_with_memory(current_components, context_memory)
        else:
            result = current_components

        # ШАГ 3: Нормализовать
        result = self._normalize_components(result)

        # ШАГ 4: Рассчитать confidence (0-1)
        parts = sum(1 for v in [result.get('street'), result.get('house_number'),
                               result.get('apartment_number')] if v)
        result['confidence'] = min(1.0, parts / 3.0)

        return result

    def _parse_address_text(self, text: str) -> Dict:
        """
        Парсит текущее сообщение на предмет адресных компонентов.

        Args:
            text: Текст сообщения

        Returns:
            Dict: Компоненты адреса из ТЕКУЩЕГО сообщения только
        """
        result = {
            'street': None,
            'house_number': None,
            'apartment_number': None,
            'entrance': None
        }

        try:
            text_lower = text.lower()

            # 1. УЛИЦА - регулярные выражения
            street_patterns = [
                r'(?:улица|ул\.?|ул|пр\.|проспект|пер\.|переулок|бул\.|бульвар)\s+([^,\d]+?)(?=\s+д\.|,|\s*$|\s+\d)',
                r'(?:на|в)\s+(?:улице|ул\.?)\s+([^,]+?)(?=\s+д\.|,|\s*$|\s+\d)',
                r'([^,\s]+(?:ая|ое|ий|ые|ая))\s+(?:улица|ул\.?)',
                # Для формата "пр. Черноморский"
                r'(?:пр\.?|проспект)\s+([А-Яа-я-]+)(?=\s+|$|,|\d)',
                # Для формата "пер. Цветочный"
                r'(?:пер\.?|переулок)\s+([А-Яа-я-]+)(?=\s+|$|,|\d)',
                # Для формата "бульвар Победы"
                r'(?:бул\.?|бульвар)\s+([А-Яа-я-]+)(?=\s+|$|,|\d)',
            ]

            for pattern in street_patterns:
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    street = match.group(1).strip()
                    # Убираем лишние слова
                    street = re.sub(r'\b(?:улица|ул|проспект)\b', '', street).strip()
                    if street:
                        result['street'] = street.capitalize()
                        logger.debug(f"Found street: {street}")
                        break

            # 2. ДОМ - регулярные выражения
            house_patterns = [
                r'(?:дом|д\.?|строение)\s+(\d+[а-яА-Я/]*)',
                r'(?:улица|ул\.?|проспект|пр\.?|пер\.?|переулок|бул\.?|бульвар)\s+[^,]+?\s+(\d+[а-яА-Я/]*)',
                r'(?:№\s*|номер\s+)(\d+[а-яА-Я/]*)',
                r'(\d+[а-яА-Я/]+)(?=\s*$|\s+кв|\s*[,;])',
                r'(?:д\.?|дом)\s+(\d+[а-яА-Я/]*)',
                # Для формата "пр. Черноморский 10"
                r'(?:пр\.?|проспект)\s+([А-Яа-я-]+)\s+(\d+[а-яА-Я/]*)',
                # Для формата "7/3" в конце строки
                r'\b(\d+[а-яА-Я/]+)\b(?=\s*$|\s+кв|\s*[,;])',
            ]

            for pattern in house_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    result['house_number'] = match.group(1)
                    logger.debug(f"Found house number: {result['house_number']}")
                    break

            # 3. КВАРТИРА - регулярное выражение
            apt_match = re.search(r'(?:кв\.?|квартира)\s+(\d+)', text, re.IGNORECASE)
            if apt_match:
                result['apartment_number'] = apt_match.group(1)
                logger.debug(f"Found apartment: {result['apartment_number']}")

            # 4. ПОДЪЕЗД - регулярное выражение
            entrance_match = re.search(r'(?:подъезд|подъ\.?|выход)\s+(\d+)', text, re.IGNORECASE)
            if entrance_match:
                result['entrance'] = entrance_match.group(1)
                logger.debug(f"Found entrance: {result['entrance']}")

        except Exception as e:
            logger.error(f"Error parsing address text '{text}': {e}")

        return result

    def _merge_with_memory(self, current: Dict, memory: Dict) -> Dict:
        """
        КЛЮЧЕВОЙ МЕТОД!!! Объединить компоненты адреса с памятью.

        Args:
            current: Компоненты извлеченные из текущего сообщения
            memory: Компоненты из DialogMemoryManager.extracted_entities

        Returns:
            Dict: Объединенные компоненты

        Пример:
        -------
        Message 1: "ул. Ленина"
        current = {street: 'Ленина', house: None, ...}
        memory = {street: None, house: None, ...}
        → result = {street: 'Ленина', house: None, ...}

        Message 2: "дом 5"
        current = {street: None, house: '5', ...}
        memory = {street: 'Ленина', house: None, ...}  ← сохранилось!
        → result = {street: 'Ленина', house: '5', ...}  ← ОБЪЕДИНЕНО!

        Message 3: "кв. 12"
        current = {street: None, house: None, apartment: '12', ...}
        memory = {street: 'Ленина', house: '5', apartment: None, ...}
        → result = {street: 'Ленина', house: '5', apartment: '12', ...}  ← ПОЛНЫЙ АДРЕС!
        """
        try:
            result = {}

            # Приоритет: текущее сообщение (current) ИЛИ память (memory)
            for key in ['street', 'house_number', 'apartment_number', 'entrance']:
                result[key] = current.get(key) or memory.get(key)

            # Отметить, восстановлено ли из памяти
            result['from_memory'] = any(
                not current.get(k) and memory.get(k)
                for k in ['street', 'house_number', 'apartment_number', 'entrance']
            )

            logger.info(f"Merged address components: {result}")
            return result

        except Exception as e:
            logger.error(f"Error merging address components: {e}")
            return current or memory

    def _normalize_components(self, components: Dict) -> Dict:
        """
        Нормализует компоненты адреса.

        Args:
            components: Сырые компоненты адреса

        Returns:
            Dict: Нормализованные компоненты
        """
        try:
            normalized = components.copy()

            # Нормализация улицы
            if normalized.get('street'):
                street = normalized['street']
                street = street.strip()
                street = re.sub(r'["\']', '', street)  # Убираем кавычки
                street = re.sub(r'\s+', ' ', street)    # Убираем лишние пробелы
                # Дополнительно убираем все пробелы в начале и в конце
                street = street.strip()
                normalized['street'] = street

            # Нормализация дома
            if normalized.get('house_number'):
                house = normalized['house_number']
                house = re.sub(r'^№\s*', '', house)     # Убираем символ №
                house = house.strip()
                normalized['house_number'] = house

            # Нормализация квартиры
            if normalized.get('apartment_number'):
                apt = normalized['apartment_number'].strip()
                normalized['apartment_number'] = apt

            # Нормализация подъезда
            if normalized.get('entrance'):
                entrance = normalized['entrance'].strip()
                normalized['entrance'] = entrance

            return normalized

        except Exception as e:
            logger.error(f"Error normalizing address components: {e}")
            return components

    def validate_and_match_to_db(self, address_components: Dict) -> Dict:
        """Валидируем адрес и ищем в БД с опечатками"""

        street = address_components.get('street')
        house_number = address_components.get('house_number')
        apartment_number = address_components.get('apartment_number')

        if not street or not house_number:
            return {
                'found': False,
                'building_id': None,
                'unit_id': None,
                'confidence': 0.0,
                'reason': 'Отсутствует улица или номер дома'
            }

        try:
            with connection.cursor() as cursor:
                # Ищем улицу (с нечетким поиском)
                cursor.execute("""
                    SELECT ao.ao_id, ao.name
                    FROM kladr_address_objects ao
                    WHERE LOWER(ao.name) LIKE LOWER(%s)
                    ORDER BY SIMILARITY(LOWER(ao.name), LOWER(%s)) DESC
                    LIMIT 3
                """, [f'%{street}%', street])

                street_results = cursor.fetchall()

                if not street_results:
                    return {
                        'found': False,
                        'building_id': None,
                        'unit_id': None,
                        'reason': f'Улица "{street}" не найдена',
                        'confidence': 0.0
                    }

                # Берем первую найденную улицу
                street_id, street_name = street_results[0]

                # Ищем здание
                cursor.execute("""
                    SELECT building_id
                    FROM buildings
                    WHERE parent_ao_id = %s
                      AND house_number ILIKE %s
                """, [street_id, house_number])

                building_result = cursor.fetchone()

                if not building_result:
                    return {
                        'found': False,
                        'building_id': None,
                        'unit_id': None,
                        'reason': f'Дом "{house_number}" на улице "{street}" не найден',
                        'confidence': 0.5
                    }

                building_id = building_result[0]

                # Ищем квартиру
                unit_id = None
                if apartment_number:
                    cursor.execute("""
                        SELECT unit_id
                        FROM units
                        WHERE building_id = %s
                          AND unit_number = %s
                    """, [building_id, apartment_number])

                    unit_result = cursor.fetchone()
                    unit_id = unit_result[0] if unit_result else None

                confidence = 0.9 if unit_id else 0.7

                return {
                    'found': True,
                    'building_id': building_id,
                    'unit_id': unit_id,
                    'street_name': street_name,
                    'address_full': f"ул. {street_name}, д. {house_number}" +
                                  (f", кв. {apartment_number}" if apartment_number else ""),
                    'confidence': confidence
                }
        except Exception as e:
            logger.error(f"Ошибка в validate_and_match_to_db: {e}")
            return {
                'found': False,
                'building_id': None,
                'unit_id': None,
                'reason': f'Ошибка базы данных: {str(e)}',
                'confidence': 0.0
            }

    def ask_clarification_if_needed(self, address_components: Dict, validation_result: Dict) -> Dict:
        """Если confidence < 0.8, просим уточнить адрес"""

        confidence = validation_result.get('confidence', 0.0)

        if confidence >= 0.8:
            return {
                'need_clarification': False,
                'message': None
            }

        missing_parts = []
        if not address_components.get('street'):
            missing_parts.append('название улицы')
        if not address_components.get('house_number'):
            missing_parts.append('номер дома')

        if missing_parts:
            message = f"Пожалуйста, укажите: {', '.join(missing_parts)}"
        elif validation_result.get('reason'):
            message = f"Адрес не найден: {validation_result['reason']}. Пожалуйста, проверьте правильность написания."
        else:
            message = "Пожалуйста, уточните адрес (улица и номер дома)"

        return {
            'need_clarification': True,
            'message': message,
            'missing_parts': missing_parts
        }