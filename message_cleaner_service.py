#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MessageCleanerService - сервис очистки сообщений от мусора

Функции:
1. Удаление приветствий (привет, здравствуйте и т.д.)
2. Удаление незначащих слов (предлоги, союзы в начале)
3. Умная очистка через LLM при необходимости
4. Сохранение ключевого смысла сообщения

Правила (из CLAUDE.md):
- КРИТИЧЕСКИ ВАЖНО: Все коммуникации на РУССКОМ языке
- ЗАПРЕЩЕНО: Использовать эмодзи
- Стиль: прямой, деловой, по делу
"""

import logging
import re
from typing import Dict, Optional, Tuple
import pymorphy2

logger = logging.getLogger(__name__)


class MessageCleanerService:
    """
    Сервис очистки сообщений от мусора перед передачей в поиск

    Логика:
    1. Базовая очистка - удаление явных приветствий
    2. Удаление стоп-слов в начале сообщения
    3. LLM-очистка (опционально) для сложных случаев
    4. ИСПРАВЛЕНО (2025-12-25): Коррекция опечаток
    """

    # Списки приветствий для очистки
    GREETINGS = [
        'привет', 'здравствуй', 'здравствуйте', 'добрый день',
        'доброе утро', 'добрый вечер', 'доброй ночи', 'хай',
        'хей', 'hello', 'hi', 'салют', 'приветствую',
        'доброго времени суток', 'доброго дня'
    ]

    # ИСПРАВЛЕНО (2026-01-12): Частые опечатки в приветствиях
    COMMON_TYPO_GREETINGS = {
        'приет': 'привет',
        'привт': 'привет',
        'привит': 'привет',
        'здрасте': 'здравствуйте',
        'здраствуйте': 'здравствуйте',
        'дарова': 'привет',
        'добрай день': 'добрый день',
        'дрбрый день': 'добрый день',
    }

    # ИСПРАВЛЕНО (2025-12-25): Частые опечатки и их исправления
    # ИСПРАВЛЕНО (2026-01-15): УБРАНО - теперь используем LLM для исправления опечаток
    # Хардкод словаря заменен на YandexGPT Lite (метод _correct_typos)

    # Слова-заполнители, не несущие смысла
    FILLER_WORDS = [
        'короче', 'типа', 'как бы', 'вроде', 'примерно',
        'смотрите', 'послушайте', 'знаете', 'видите ли'
    ]

    # Стоп-слова в начале (предлоги, союзы, местоимения)
    PREFIX_STOP_WORDS = [
        'а', 'но', 'да', 'нет', 'ну', 'же', 'ли', 'ведь',
        'просто', 'просто-', 'лишь', 'только', 'честно',
        'вообще', 'в принципе', 'собственно', 'итак'
    ]

    def __init__(self, ai_agent_service=None):
        """
        Инициализация сервиса

        Args:
            ai_agent_service: Опционально, сервис для LLM-очистки
        """
        self.ai_agent = ai_agent_service
        logger.info("MessageCleanerService инициализирован")

    async def clean_message(self, message_text: str, use_llm: bool = False) -> Tuple[str, Dict]:
        """
        Очистка сообщения от мусора

        ИСПРАВЛЕНО (2026-01-15): Сделан async для LLM-коррекции опечаток

        Args:
            message_text: Исходный текст сообщения
            use_llm: Использовать LLM для очистки (если False - только базовая очистка)

        Returns:
            Tuple[str, Dict]: (очищенный текст, метаданные очистки)
                {
                    'original_length': int,
                    'cleaned_length': int,
                    'removed_greeting': bool,
                    'removed_fillers': bool,
                    'removed_prefixes': bool,
                    'llm_used': bool
                }
        """
        if not message_text or not isinstance(message_text, str):
            return message_text, {'error': 'Invalid input'}

        original_text = message_text
        cleaned_text = message_text.strip()
        metadata = {
            'original_length': len(original_text),
            'cleaned_length': len(cleaned_text),
            'removed_greeting': False,
            'removed_fillers': False,
            'removed_prefixes': False,
            'llm_used': False
        }

        # Шаг 1: Базовая очистка - удаление приветствий
        cleaned_text = self._remove_greetings(cleaned_text)
        if cleaned_text != original_text.strip():
            metadata['removed_greeting'] = True

        # ИСПРАВЛЕНО (2025-12-25): Шаг 1.5 - Коррекция опечаток
        # ИСПРАВЛЕНО (2026-01-15): Добавлен await для async _correct_typos
        cleaned_text = await self._correct_typos(cleaned_text)
        if cleaned_text != original_text.strip():
            metadata['typos_corrected'] = True
            metadata['original'] = original_text.strip()
            metadata['corrected'] = cleaned_text

        # Шаг 2: Удаление слов-заполнителей
        before_filler = cleaned_text
        cleaned_text = self._remove_filler_words(cleaned_text)
        if cleaned_text != before_filler:
            metadata['removed_fillers'] = True

        # Шаг 3: Удаление стоп-слов в начале
        before_prefix = cleaned_text
        cleaned_text = self._remove_prefix_stop_words(cleaned_text)
        if cleaned_text != before_prefix:
            metadata['removed_prefixes'] = True

        # Шаг 4: LLM-очистка (если включено и доступен AI)
        if use_llm and self.ai_agent:
            cleaned_text = await self._llm_clean(cleaned_text, metadata)

        # Финальная зачистка
        cleaned_text = cleaned_text.strip()
        metadata['cleaned_length'] = len(cleaned_text)

        # Логируем результат
        removed_pct = (1 - len(cleaned_text) / len(original_text)) * 100 if original_text else 0
        if removed_pct > 10:  # Логируем только если удалили >10%
            logger.info(
                f"Очистка сообщения: удалили {removed_pct:.1f}% "
                f"(исходная длина: {len(original_text)}, итоговая: {len(cleaned_text)})"
            )

        return cleaned_text, metadata

    def _remove_greetings(self, text: str) -> str:
        """
        Удаление приветствий из начала сообщения

        Паттерны:
        - "Привет! У меня..." -> "У меня..."
        - "Здравствуйте, у меня..." -> "у меня..."
        - "Добрый день. Проблема..." -> "Проблема..."
        """
        lines = text.split('\n')
        first_line = lines[0].strip()

        for greeting in self.GREETINGS:
            # Проверяем начало строки
            patterns = [
                f'^{re.escape(greeting)}[!,.\\s]+',
                f'^{re.escape(greeting)}\\s+[!,.]*\\s*',
            ]

            for pattern in patterns:
                match = re.match(pattern, first_line, re.IGNORECASE)
                if match:
                    # Удаляем приветствие
                    first_line = first_line[match.end():].strip()
                    # Если первая строка стала пустой - удаляем её
                    if not first_line and len(lines) > 1:
                        lines = lines[1:]
                    else:
                        lines[0] = first_line
                    return '\n'.join(lines)

        return text

    def _remove_filler_words(self, text: str) -> str:
        """
        Удаление слов-заполнителей

        Паттерны:
        - "Короче, у меня..." -> "у меня..."
        - "Смотрите, проблема..." -> "проблема..."
        """
        cleaned = text

        for filler in self.FILLER_WORDS:
            # Удаляем с запятой или без
            patterns = [
                f'\\b{re.escape(filler)},?\\s+',
                f'\\b{re.escape(filler)}-?\\s+',
            ]

            for pattern in patterns:
                cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)

        return cleaned.strip()

    def _remove_prefix_stop_words(self, text: str) -> str:
        """
        Удаление стоп-слов в начале сообщения

        Паттерны:
        - "А у меня..." -> "у меня..."
        - "Просто проблема..." -> "проблема..."
        - "Ну вообще..." -> "вообще..." (или удалено если далее ключевое слово)
        """
        words = text.split()

        # Удаляем стоп-слова из начала (максимум 3 подряд)
        removed_count = 0
        max_prefix_removal = 3

        for word in words[:max_prefix_removal + 5]:
            if removed_count >= max_prefix_removal:
                break

            word_lower = word.lower().strip(',!?.-')
            if word_lower in self.PREFIX_STOP_WORDS:
                removed_count += 1
            else:
                break

        if removed_count > 0:
            return ' '.join(words[removed_count:])

        return text

    async def _llm_clean(self, text: str, metadata: Dict) -> str:
        """
        Умная очистка через LLM

        Используется для сложных случаев когда базовая очистка недостаточна
        """
        try:
            prompt = f'''Задача: Очистить текст сообщения от лишних слов и сохранить только суть проблемы.

Исходный текст: "{text}"

Инструкция:
1. Удали приветствия, вежливости, извинения
2. Удали слова-заполнители (короче, типа, как бы)
3. Удали вводные конструкции (вообще, в принципе, честно говоря)
4. СОХРАНИ ключевые слова: что сломалось, где проблема, симптомы
5. Верни ТОЛЬКО очищенный текст, без объяснений

Примеры:
- "Привет! У меня течет кран" -> "течет кран"
- "Добрый день, извините, просто у меня проблема с отоплением" -> "проблема с отоплением"
- "Здравствуйте, вообще-то в ванной засорился слив" -> "в ванной засорился слив"

Очищенный текст:'''

            # Вызываем LLM через AIAgentService
            response, usage = await self.ai_agent._call_yandex_gpt(prompt)

            if response:
                cleaned = response.strip()
                metadata['llm_used'] = True
                logger.info(f"LLM очистка: '{text[:30]}...' -> '{cleaned[:30]}...'")
                return cleaned

        except Exception as e:
            logger.error(f"Ошибка LLM очистки: {e}")

        return text

    def is_greeting_only(self, text: str) -> bool:
        """
        Проверка: является ли сообщение только приветствием

        ИСПРАВЛЕНО (2026-01-12): Добавлено распознавание опечаток
        - "приет" → "привет"
        - "здрасте" → "здравствуйте"
        - "дрбрый день" → "добрый день"

        Args:
            text: Текст сообщения

        Returns:
            bool: True если сообщение только приветствие
        """
        if not text:
            return False

        cleaned = text.strip().lower()
        words = re.findall(r'\b\w+\b', cleaned)

        # Если слов мало и все они приветствия
        if len(words) <= 3:
            greeting_words = [w for w in words if self._is_greeting_word(w)]
            if len(greeting_words) == len(words):
                return True

        return False

    def _is_greeting_word(self, word: str) -> bool:
        """
        Проверяет является ли слово приветствием (с опечатками)

        ИСПРАВЛЕНО (2026-01-12): Добавлено распознавание опечаток

        Args:
            word: Слово для проверки

        Returns:
            bool: True если слово является приветствием
        """
        # ИСПРАВЛЕНО (2026-01-12): Проверка частых опечаток
        if word in self.COMMON_TYPO_GREETINGS:
            return True

        # Точное совпадение
        if any(g == word for g in self.GREETINGS):
            return True

        # Проверка на вхождение (для "привет" внутри "приветики")
        if any(g in word or word in g for g in self.GREETINGS if len(g) > 4):
            return True

        # ИСПРАВЛЕНО (2026-01-12): Нечеткое сравнение для частых опечаток
        # Проверяем расстояние Левенштейна для слов похожей длины
        for greeting in self.GREETINGS:
            # ИСПРАВЛЕНИЕ: Более мягкий порог для длины
            if abs(len(word) - len(greeting)) <= max(3, len(greeting) * 0.4):
                # Если слова похожей длины - проверяем нечеткое совпадение
                if self._fuzzy_match(word, greeting, threshold=0.65):
                    return True

        return False

    def _fuzzy_match(self, s1: str, s2: str, threshold: float = 0.7) -> bool:
        """
        Нечеткое сравнение строк на основе расстояния Левенштейна

        ИСПРАВЛЕНО (2026-01-12): Добавлено для распознавания опечаток

        Args:
            s1: Первая строка
            s2: Вторая строка
            threshold: Порог схожести (0.0 - 1.0)

        Returns:
            bool: True если строки похожи
        """
        if not s1 or not s2:
            return False

        # Простое расстояние Левенштейна
        len1, len2 = len(s1), len(s2)

        # Если разница в длине слишком большая - не совпадает
        if abs(len1 - len2) > max(len1, len2) * (1 - threshold):
            return False

        # Вычисляем расстояние Левенштейна
        if len1 < len2:
            s1, s2 = s2, s1
            len1, len2 = len2, len1

        # s1 всегда длиннее или равен s2
        previous_row = list(range(len2 + 1))

        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        distance = previous_row[-1]
        max_len = max(len1, len2)

        # Нормализуем расстояние
        similarity = 1 - (distance / max_len) if max_len > 0 else 0

        return similarity >= threshold

    def get_meaningful_words(self, text: str) -> list:
        """
        Извлечение значимых слов из сообщения

        Удаляет:
        - Предлоги
        - Союзы
        - Местоимения
        - Вспомогательные глаголы

        Args:
            text: Текст сообщения

        Returns:
            list: Список значимых слов
        """
        if not text:
            return []

        # Базовый список стоп-слов (можно расширить)
        stop_words = {
            'и', 'в', 'во', 'не', 'что', 'он', 'на', 'с', 'я',
            'как', 'а', 'то', 'все', 'она', 'так', 'его', 'из',
            'у', 'же', 'вы', 'за', 'бы', 'по', 'только', 'ее',
            'мне', 'было', 'вот', 'от', 'меня', 'еще', 'нет',
            'о', 'из', 'ему', 'теперь', 'когда', 'даже', 'ну',
            'вдруг', 'ли', 'если', 'уже', 'или', 'ни', 'быть',
            'был', 'него', 'до', 'вас', 'нибудь', 'опять', 'уж',
            'вам', 'ведь', 'там', 'потом', 'себя', 'ничего', 'ей',
            'может', 'они', 'тут', 'где', 'есть', 'надо', 'ней',
            'для', 'мы', 'тебя', 'их', 'чем', 'была', 'сам', 'чтоб'
        }

        words = re.findall(r'\b\w+\b', text.lower())
        meaningful = [w for w in words if w not in stop_words and len(w) > 2]

        return meaningful

    async def _correct_typos(self, text: str) -> str:
        """
        ИСПРАВЛЕНО (2026-01-15): Коррекция опечаток через YandexGPT Lite

        Заменяет хардкод словаря на LLM-анализ текста.
        Исправляет опечатки типа:
        - "комфорок" → "конфорок"
        - "тетчет" → "течет"
        - "не приятно" → "неприятно"

        Args:
            text: Исходный текст с возможными опечатками

        Returns:
            str: Исправленный текст
        """
        if not text or not self.ai_agent:
            return text

        # Если текст короткий и без явных опечаток - пропускаем
        if len(text) < 10:
            return text

        try:
            prompt = f"""Ты - корректор русского языка. Исправь опечатки в тексте.

ТЕКСТ С ОПЕЧАТКАМИ:
{text}

ПРАВИЛА:
1. Исправь только ЯВНЫЕ опечатки
2. Сохраняй смысл и стиль сообщения
3. НЕ меняй сленг и разговорные выражения (если они уместны)
4. НЕ добавляй и НЕ удаляй слова
5. Верни ТОЛЬКО исправленный текст, без объяснений

Исправленный текст:"""

            response, _ = await self.ai_agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite'
            )

            corrected = response.strip()

            if corrected and corrected != text:
                logger.info(f"LLM-коррекция: '{text[:50]}...' → '{corrected[:50]}...'")
                return corrected

            return text

        except Exception as e:
            logger.warning(f"Ошибка LLM-коррекции опечаток: {e}")
            return text


# Для тестирования
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    cleaner = MessageCleanerService()

    test_messages = [
        "Привет! У меня течет кран на кухне",
        "Здравствуйте, добрый день, у меня проблема с отоплением",
        "Короче, у меня в ванной засор",
        "Просто вообще-то как бы у меня сломался лифт",
        "Ну вообще в подъезде нет света",
        "Добрый вечер. Извините, у меня течет труба в квартире",
        "привет",
        "Здравствуйте, подскажите пожалуйста",
    ]

    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ОЧИСТКИ СООБЩЕНИЙ")
    print("=" * 60)

    for msg in test_messages:
        cleaned, meta = await cleaner.clean_message(msg)

        print(f"\nИсходное:  '{msg}'")
        print(f"Очищенное: '{cleaned}'")
        print(f"Метаданные: {meta}")

        if cleaner.is_greeting_only(msg):
            print(">>> ТОЛЬКО ПРИВЕТСТВИЕ")
