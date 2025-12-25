#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестирование морфологических улучшений TagSearchV2 и SemanticSearch
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

from tag_search_service_v2 import TagSearchServiceV2
from semantic_search_service import SemanticSearchService

async def test_morphology_improvements():
    """Тестируем улучшения с морфологией"""

    # Настройка логирования
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    print("=== ТЕСТИРОВАНИЕ МОФОЛОГИЧЕСКИХ УЛУЧШЕНИЙ ===\n")

    # Тестируемые фразы
    test_phrases = [
        "течет труба",
        "у меня течет",
        "сломался лифт",
        "перегорела лампочка",
        "нет отопления"
    ]

    # Создаем экземпляры сервисов
    tag_search = TagSearchServiceV2()
    semantic_search = SemanticSearchService()

    # Загружаем услуги
    await tag_search._load_services()
    await semantic_search._load_services()

    for phrase in test_phrases:
        print(f"\n{'='*60}")
        print(f"ТЕСТИРУЕМАЯ ФРАЗА: '{phrase}'")
        print(f"{'='*60}")

        # Тестируем TagSearchV2
        print(f"\n--- TagSearchV2 ---")
        tag_result = await tag_search.search(phrase)
        print(f"Найдено кандидатов: {len(tag_result.get('candidates', []))}")
        for i, candidate in enumerate(tag_result.get('candidates', []), 1):
            print(f"{i}. Услуга ID {candidate['service_id']}: {candidate['service_name']} (уверенность: {candidate['confidence']})")

        # Тестируем SemanticSearch
        print(f"\n--- SemanticSearch ---")
        semantic_result = await semantic_search.search(phrase)
        print(f"Найдено кандидатов: {len(semantic_result.get('candidates', []))}")
        for i, candidate in enumerate(semantic_result.get('candidates', []), 1):
            print(f"{i}. Услуга ID {candidate['service_id']}: {candidate['service_name']} (уверенность: {candidate['confidence']})")

        # Показываем морфологический анализ
        print(f"\n--- Морфологический анализ ---")
        normalized_words = tag_search._normalize_text_with_morphology(phrase)
        print(f"Нормализованные слова: {normalized_words}")

        # Семантические признаки
        features = semantic_search._analyze_semantic_features(phrase)
        if features:
            print("Найденные семантические признаки:")
            for feature_name, feature_data in features.items():
                print(f"  {feature_name}: уверенность {feature_data['confidence']}, "
                      f"совпадений {feature_data['total_matches']} "
                      f"(обычных: {feature_data['matches']}, нормализованных: {feature_data['normalized_matches']})")
        else:
            print("Семантических признаков не найдено")

if __name__ == "__main__":
    asyncio.run(test_morphology_improvements())