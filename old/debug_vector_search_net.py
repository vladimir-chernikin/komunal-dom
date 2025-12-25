#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Анализ работы VectorSearchService для сообщения "нет"
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

from vector_search_service import VectorSearchService

async def test_vector_search_net():
    """Тестируем векторный поиск для слова 'нет'"""

    # Настройка логирования
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Создаем экземпляр VectorSearchService
    vector_search = VectorSearchService()

    # Загружаем услуги
    await vector_search._load_services()

    print("=== АНАЛИЗ ВЕКТОРНОГО ПОИСКА ДЛЯ ФРАЗЫ 'НЕТ' ===\n")

    message_text = "нет"
    result = await vector_search.search(message_text)

    print(f"РЕЗУЛЬТАТ ПОИСКА ДЛЯ '{message_text}':")
    print(f"Статус: {result['status']}")
    print(f"Найдено кандидатов: {result.get('total_matches', 0)}")
    print()

    # Показываем детали расчета для каждой услуги
    import re
    from rapidfuzz import fuzz

    message_words = re.findall(r'\b\w+\b', message_text.lower())
    message_text_norm = ' '.join(message_words)

    print("ДЕТАЛЬНЫЙ РАСЧЕТ ДЛЯ КАЖДОЙ УСЛУГИ:")
    print("=" * 60)

    for service_id, service_info in vector_search.service_cache.items():
        search_vector = service_info['search_vector']
        search_terms = service_info['search_terms']

        print(f"\nУСЛУГА ID {service_id}: {service_info['name']}")
        print(f"Поисковые термины: {search_terms}")

        # Расчет семантической близости
        partial_ratio = fuzz.partial_ratio(message_text_norm, search_vector) / 100.0
        token_set_ratio = fuzz.token_set_ratio(message_text_norm, search_vector) / 100.0

        print(f"Partial Ratio: {partial_ratio:.3f}")
        print(f"Token Set Ratio: {token_set_ratio:.3f}")

        # Дополнительные очки за совпадение терминов
        term_matches = 0
        matched_terms = []
        for word in message_words:
            for term in search_terms:
                if fuzz.ratio(word, term.lower()) >= 80:
                    term_matches += 1
                    matched_terms.append(f"'{word}' ~ '{term}'")

        print(f"Совпавшие термины: {matched_terms}")
        print(f"Количество совпадений терминов: {term_matches}")

        # Комбинированная оценка
        term_score = min(term_matches / max(len(message_words), 1), 1.0)
        confidence = max(partial_ratio, token_set_ratio) * 0.6 + (term_score * 0.4)

        print(f"Term Score: {term_score:.3f}")
        print(f"Итоговая уверенность: {confidence:.3f}")
        print(f"Выше порога 0.6? {'Да' if confidence >= 0.6 else 'Нет'}")

    print("\n" + "=" * 60)
    print("ИТОГОВЫЕ КАНДИДАТЫ:")
    for i, candidate in enumerate(result.get('candidates', []), 1):
        print(f"{i}. Услуга ID {candidate['service_id']}: {candidate['service_name']} (уверенность: {candidate['confidence']})")

if __name__ == "__main__":
    asyncio.run(test_vector_search_net())