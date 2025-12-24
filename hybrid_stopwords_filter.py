#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
HybridStopWordsFilter - гибридная фильтрация стоп-слов
Комбинация базовых, контекстных, морфологических правил
"""

import logging
import re
import pymorphy2
from typing import List, Set, Dict, Optional

logger = logging.getLogger(__name__)


class HybridStopWordsFilter:
    """Гибридный фильтр стоп-слов для русского языка"""

    def __init__(self):
        self.morph = None  # Ленивая инициализация
        self._initialize_filters()
        logger.info("HybridStopWordsFilter инициализирован")

    def _get_morph(self):
        """Ленивая инициализация морфологического анализатора"""
        if self.morph is None:
            self.morph = pymorphy2.MorphAnalyzer()
        return self.morph

    def _initialize_filters(self):
        """Инициализация всех типов фильтров"""

        # 1. Базовые стоп-слова русского языка
        self.basic_stop_words = {
            # Союзы и частицы
            'и', 'в', 'во', 'не', 'на', 'с', 'со', 'но', 'а', 'или', 'либо', 'то', 'же',
            'как', 'что', 'кто', 'где', 'когда', 'почему', 'зачем', 'какой', 'какая',
            'этот', 'эта', 'это', 'тот', 'та', 'то', 'те', 'все', 'вся', 'весь',

            # Предлоги
            'без', 'до', 'для', 'за', 'из', 'к', 'ко', 'между', 'от', 'по', 'под',
            'при', 'про', 'против', 'ради', 'раз', 'через', 'чтоб', 'чтобы',

            # Вводные слова и междометия
            'да', 'нет', 'угу', 'ага', 'неа', 'конечно', 'может', 'может быть', 'наверное',

            # Вежливости и формальности
            'пожалуйста', 'спасибо', 'извините', 'благодарю', 'привет', 'здравствуйте',
            'до свидания', 'добрый день', 'добрый вечер',

            # Универсальные слабоинформативные слова
            'сейчас', 'теперь', 'здесь', 'там', 'сюда', 'туда', 'вчера', 'завтра', 'сегодня',

            # Короткие слова (менее 2 символов)
            'я', 'ты', 'он', 'она', 'оно', 'мы', 'вы', 'они', 'у', 'к', 'о', 'об'
        }

        # 2. Контекстные стоп-слова для ЖКХ
        self.contextual_stop_words = {
            'water_problem': ['вода', 'жидкость', 'жидкостный'],  # Если уже определена проблема с водой
            'electricity_problem': ['свет', 'электричество', 'напряжение'],  # Если проблема с электричеством
            'heating_problem': ['тепло', 'батарея', 'отопление'],  # Если проблема с отоплением
            'request_type': ['проблема', 'вопрос', 'запрос', 'обращение'],  # Слова типа проблемы
            'location_general': ['адрес', 'место', 'участок', 'территория'],  # Общие локации
        }

        # 3. Профессиональные синонимы в ЖКХ
        self.jkh_synonyms = {
            'течь': ['протечка', 'утечка', 'подтапливание', 'протекает', 'течет', 'льется'],
            'засор': ['пробка', 'закупорка', 'забито', 'непроходимость', 'засорение'],
            'поломка': ['неисправность', 'отказ', 'авария', 'сбой', 'дефект'],
            'отопление': ['батарея', 'радиатор', 'теплосеть', 'подача тепла', 'нагрев'],
        }

        # 4. Части речи для фильтрации
        self.allowed_pos_tags = {
            'NOUN',    # существительные
            'VERB',    # глаголы
            'INFN',    # инфинитивы
            'ADJF',    # полные прилагательные
            'ADJS',    # краткие прилагательные
            'PRTF',    # полные причастия
            'PRTS',    # краткие причастия
            'NUMR',    # числительные
            'ADVB',    # наречия
            'PRED'     # предикативы
        }

        # 5. Проблемные слова и их варианты
        self.problem_words = {
            'water_leak': ['течь', 'протекать', 'капать', 'лить', 'утечка', 'протечка', 'сырость', 'влага'],
            'clog': ['засор', 'забить', 'пробка', 'закупорить', 'непроходимость'],
            'breakage': ['сломать', 'повредить', 'испортить', 'поломка', 'авария', 'неисправность'],
            'no_service': ['нет', 'отсутствует', 'перестало', 'прекратилось'],
        }

    def filter_text(self, text: str, context: Optional[str] = None) -> List[str]:
        """
        Основной метод фильтрации текста

        Args:
            text: Исходный текст
            context: Контекст (water_problem, electricity_problem и т.д.)

        Returns:
            List[str]: Отфильтрованные значимые слова
        """
        try:
            # 1. Токенизация и базовая очистка
            tokens = self._tokenize_and_clean(text)
            logger.info(f"Токенизация: {len(tokens)} токенов из '{text}'")

            # 2. Базовая фильтрация стоп-слов
            tokens = self._basic_filter(tokens)
            logger.info(f"После базовой фильтрации: {len(tokens)} токенов")

            # 3. Контекстная фильтрация
            if context:
                tokens = self._contextual_filter(tokens, context)
                logger.info(f"После контекстной фильтрации: {len(tokens)} токенов")

            # 4. Морфологическая фильтрация
            tokens = self._morphological_filter(tokens)
            logger.info(f"После морфологической фильтрации: {len(tokens)} токенов")

            # 5. Проблемно-ориентированная фильтрация
            tokens = self._problem_oriented_filter(tokens)
            logger.info(f"Финальный результат: {tokens}")

            return tokens

        except Exception as e:
            logger.error(f"Ошибка фильтрации текста: {e}")
            return self._tokenize_and_clean(text)  # Возвращаем базовую токенизацию

    def _tokenize_and_clean(self, text: str) -> List[str]:
        """Токенизация и базовая очистка текста"""
        # Приводим к нижнему регистру
        text = text.lower()

        # Удаляем знаки препинания и цифры
        text = re.sub(r'[^\w\s]', ' ', text)
        text = re.sub(r'\d+', '', text)

        # Разбиваем на слова
        words = text.split()

        # Фильтрация по длине (оставляем слова от 2 до 20 символов)
        filtered_words = []
        for word in words:
            if 2 <= len(word) <= 20:
                filtered_words.append(word.strip())

        return filtered_words

    def _basic_filter(self, tokens: List[str]) -> List[str]:
        """Базовая фильтрация стоп-слов"""
        filtered = []
        for token in tokens:
            if token not in self.basic_stop_words:
                filtered.append(token)
        return filtered

    def _contextual_filter(self, tokens: List[str], context: str) -> List[str]:
        """Контекстно-зависимая фильтрация"""
        if context in self.contextual_stop_words:
            context_stop = self.contextual_stop_words[context]
            filtered = []
            for token in tokens:
                if token not in context_stop:
                    filtered.append(token)
            return filtered
        return tokens

    def _morphological_filter(self, tokens: List[str]) -> List[str]:
        """Морфологическая фильтрация по частям речи"""
        morph = self._get_morph()
        filtered = []

        for token in tokens:
            try:
                parsed = morph.parse(token)[0]

                # Проверяем часть речи
                pos_tag = parsed.tag.POS
                if pos_tag in self.allowed_pos_tags:
                    # Добавляем нормальную форму
                    filtered.append(parsed.normal_form)

                    # Для глаголов добавляем еще и исходную форму если отличается
                    if pos_tag == 'VERB' and parsed.normal_form != token:
                        filtered.append(token)

            except Exception as e:
                logger.warning(f"Ошибка морфологического разбора слова '{token}': {e}")
                filtered.append(token)  # Добавляем как есть если ошибка

        # Убираем дубликаты
        return list(set(filtered))

    def _problem_oriented_filter(self, tokens: List[str]) -> List[str]:
        """Проблемно-ориентированная фильтрация и обогащение"""
        filtered = []

        for token in tokens:
            # Проверяем, не является ли токен синонимом проблемного слова
            is_problem_related = False

            for problem_type, synonyms in self.problem_words.items():
                if token in synonyms:
                    # Если это синоним, добавляем основное слово проблемы
                    if problem_type in tokens:
                        # Основное слово уже есть, пропускаем синоним
                        is_problem_related = True
                        break
                    else:
                        # Добавляем основное слово проблемы
                        filtered.append(problem_type)
                        is_problem_related = True
                        break

            if not is_problem_related:
                filtered.append(token)

        return filtered

    def get_filter_statistics(self, original_text: str, context: Optional[str] = None) -> Dict:
        """
        Получить статистику фильтрации для отладки

        Args:
            original_text: Исходный текст
            context: Контекст фильтрации

        Returns:
            Dict: Статистика каждого этапа фильтрации
        """
        original_tokens = self._tokenize_and_clean(original_text)
        basic_filtered = self._basic_filter(original_tokens)

        contextual_filtered = basic_filtered
        if context:
            contextual_filtered = self._contextual_filter(basic_filtered, context)

        morphological_filtered = self._morphological_filter(contextual_filtered)
        final_filtered = self._problem_oriented_filter(morphological_filtered)

        return {
            'original_tokens_count': len(original_tokens),
            'original_tokens': original_tokens,
            'after_basic_count': len(basic_filtered),
            'after_basic': basic_filtered,
            'after_contextual_count': len(contextual_filtered),
            'after_contextual': contextual_filtered,
            'after_morphological_count': len(morphological_filtered),
            'after_morphological': morphological_filtered,
            'final_count': len(final_filtered),
            'final_tokens': final_filtered,
            'filter_efficiency': (len(original_tokens) - len(final_filtered)) / len(original_tokens) * 100 if original_tokens else 0
        }

    def add_custom_stop_words(self, words: Set[str], category: Optional[str] = None):
        """
        Добавить пользовательские стоп-слова

        Args:
            words: Набор стоп-слов для добавления
            category: Категория (basic, contextual)
        """
        if category == 'contextual':
            # Добавляем во все контекстные категории
            for context_stop in self.contextual_stop_words.values():
                context_stop.update(words)
        else:
            # Добавляем в базовые стоп-слова
            self.basic_stop_words.update(words)

        logger.info(f"Добавлено {len(words)} стоп-слов в категорию '{category or 'basic'}'")

    def add_problem_synonym(self, problem_type: str, synonyms: List[str]):
        """
        Добавить синонимы для типа проблемы

        Args:
            problem_type: Тип проблемы (water_leak, clog и т.д.)
            synonyms: Список синонимов
        """
        if problem_type not in self.problem_words:
            self.problem_words[problem_type] = []

        self.problem_words[problem_type].extend(synonyms)
        logger.info(f"Добавлены синонимы для '{problem_type}': {synonyms}")


# Пример использования и тестирования
if __name__ == "__main__":
    filter = HybridStopWordsFilter()

    test_texts = [
        "течет труба в квартире",
        "у меня не работает отопление",
        "пожалуйста помогите сломался лифт",
        "нет света пожалуйста срочно"
    ]

    for text in test_texts:
        print(f"\nТекст: {text}")
        stats = filter.get_filter_statistics(text)
        result = filter.filter_text(text)

        print(f"Оригинал: {stats['original_tokens']}")
        print(f"Результат: {result}")
        print(f"Эффективность фильтрации: {stats['filter_efficiency']:.1f}%")