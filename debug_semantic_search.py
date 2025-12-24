#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Анализ работы SemanticSearchService для сообщения "течет труба"
"""

import asyncio
import logging
import sys
import os
sys.path.append('/var/www/komunal-dom_ru')

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
import django
django.setup()

from semantic_search_service import SemanticSearchService

async def test_semantic_search():
    """Тестируем семантический поиск для фразы 'течет труба'"""

    # Настройка логирования
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Создаем экземпляр SemanticSearchService
    semantic_search = SemanticSearchService()

    print("=== АНАЛИЗ СЕМАНТИЧЕСКОГО ПОИСКА ДЛЯ ФРАЗЫ 'ТЕЧЕТ ТРУБА' ===\n")

    # Показываем семантические паттерны
    print("Семантические паттерны в системе:")
    for pattern_name, pattern_data in semantic_search.semantic_patterns.items():
        print(f"{pattern_name}:")
        print(f"  Определение: {pattern_data['definition']}")
        print(f"  Ключевые слова: {pattern_data['keywords']}")
        print(f"  Вес: {pattern_data['weight']}")
        print()

    # Анализируем текст
    message_text = "течет труба"
    features = semantic_search._analyze_semantic_features(message_text)

    print(f"РЕЗУЛЬТАТ АНАЛИЗА ФРАЗЫ '{message_text}':")
    print(f"Найдено признаков: {len(features)}")
    print()

    if features:
        for feature_name, feature_data in features.items():
            print(f"Признак: {feature_name}")
            print(f"  Уверенность: {feature_data['confidence']}")
            print(f"  Совпадения: {feature_data['matches']}")
            print(f"  Ключевые слова: {feature_data['keywords']}")
            print(f"  Определение: {feature_data['definition']}")
            print()
    else:
        print("НИ ОДНОГО ПРИЗНАКА НЕ НАЙДЕНО!")
        print()

    # Проверяем каждое ключевое слово вручную
    print("РУЧНАЯ ПРОВЕРКА КЛЮЧЕВЫХ СЛОВ:")
    text_lower = message_text.lower()
    print(f"Текст для поиска: '{text_lower}'")
    print()

    for pattern_name, pattern_data in semantic_search.semantic_patterns.items():
        print(f"\nПаттерн: {pattern_name}")
        for keyword in pattern_data['keywords']:
            if keyword in text_lower:
                print(f"  ✅ НАЙДЕНО: '{keyword}' в тексте")
            else:
                print(f"  ❌ не найдено: '{keyword}'")

if __name__ == "__main__":
    asyncio.run(test_semantic_search())