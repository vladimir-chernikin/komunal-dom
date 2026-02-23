#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Анализ порогов confidence для выбора правильного решения

Цель: Определить оптимальный порог confidence для MainAgent
на основе реальных данных测试"""

import asyncio
import sys
sys.path.append('/var/www/komunal-dom_ru')

import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
import django
django.setup()

from main_agent import MainAgent
import json
from collections import defaultdict


async def analyze_confidence_distribution():
    """Анализируем распределение confidence для правильных/неправильных услуг"""

    print("=" * 80)
    print("АНАЛИЗ ПОРОГОВ CONFIDENCE - СБОР ДОКАЗАТЕЛЬСТВ")
    print("=" * 80)

    agent = MainAgent()

    # Тестовые сценарии с ПРАВИЛЬНЫМ ответом
    test_cases = [
        # Водоснабжение - "нет" услуги
        ("нет горячей воды", 34, "Нет горячей воды во всём доме", "Водоснабжение"),
        ("нет холодной воды", 39, "Нет холодной воды во всём доме", "Водоснабжение"),
        ("нет вод горячей", 34, "Нет горячей воды во всём доме", "Водоснабжение"),

        # Водоснабжение - другие услуги
        ("прорыв трубы в квартире", 32, "Прорыв труб в квартире", "Водоснабжение"),
        ("слабый напор воды", 37, "Слабый напор воды в кране, переток гвс хвс", "Водоснабжение"),
        ("протекает кран", 38, "Протечки сантехники индивидуальное", "Водоснабжение"),

        # Отопление
        ("нет отопления", 25, "Отсутствие отопления", "Отопление"),
        ("течет батарея", 31, "Протечка батареи/радиатора в квартире", "Отопление"),

        # Электричество
        ("нет света во всем доме", 43, "Нет света во всем доме", "Электричество"),
        ("нет света", 46, "Нет света индивидуальное", "Электричество"),
        ("искрение щитка", 42, "Искрение, замыкание электрощитов и ВРУ", "Электричество"),
    ]

    results_by_category = defaultdict(list)

    print("\nТестирование сценариев...")
    print("-" * 80)

    for query, expected_id, expected_name, category in test_cases:
        try:
            result = await agent.process_service_detection(
                message_text=query,
                user_context={}
            )

            # Ищем правильную услугу в кандидатах
            found_correct = False
            correct_confidence = None
            all_confidences = []

            if 'candidates' in result:
                for cand in result['candidates']:
                    all_confidences.append(cand.get('confidence', 0))
                    if cand.get('service_id') == expected_id:
                        found_correct = True
                        correct_confidence = cand.get('confidence')

            results_by_category[category].append({
                'query': query,
                'expected_id': expected_id,
                'found': found_correct,
                'confidence': correct_confidence,
                'all_confidences': all_confidences,
                'status': result.get('status')
            })

            marker = "✅" if found_correct else "❌"
            conf_str = f"{correct_confidence:.3f}" if correct_confidence else "N/A"
            print(f"{marker} [{category}] {query:30s} → conf={conf_str} ({result.get('status')})")

        except Exception as e:
            print(f"❌ [{category}] {query:30s} → ОШИБКА: {str(e)[:50]}")

    # Анализ результатов
    print("\n" + "=" * 80)
    print("СТАТИСТИКА ПО КАТЕГОРИЯМ")
    print("=" * 80)

    for category, results in results_by_category.items():
        print(f"\n{category}:")
        print("-" * 40)

        correct_results = [r for r in results if r['found']]
        incorrect_results = [r for r in results if not r['found']]

        if correct_results:
            confidences = [r['confidence'] for r in correct_results if r['confidence']]
            if confidences:
                avg_conf = sum(confidences) / len(confidences)
                min_conf = min(confidences)
                max_conf = max(confidences)

                print(f"  Правильные находки: {len(correct_results)}/{len(results)}")
                print(f"  Confidence: средний={avg_conf:.3f}, мин={min_conf:.3f}, макс={max_conf:.3f}")

                # Анализ порога 0.9
            count_09 = len([c for c in confidences if c >= 0.9])
            count_08 = len([c for c in confidences if c >= 0.8])
            count_07 = len([c for c in confidences if c >= 0.7])

            print(f"  Распределение по порогам:")
            print(f"    >= 0.9: {count_09}/{len(confidences)} ({100*count_09/len(confidences):.1f}%)")
            print(f"    >= 0.8: {count_08}/{len(confidences)} ({100*count_08/len(confidences):.1f}%)")
            print(f"    >= 0.7: {count_07}/{len(confidences)} ({100*count_07/len(confidences):.1f}%)")

        if incorrect_results:
            print(f"  Неправильные находки: {len(incorrect_results)}")

    # Спецанализ для Водоснабжения
    print("\n" + "=" * 80)
    print("СПЕЦИАЛЬНЫЙ АНАЛИЗ: ВОДОСНАБЖЕНИЕ")
    print("=" * 80)

    water_results = results_by_category.get('Водоснабжение', [])
    water_correct = [r for r in water_results if r['found']]

    if water_correct:
        confidences = [r['confidence'] for r in water_correct if r['confidence']]

        print(f"\n Confidence для ПРАВИЛЬНЫХ услуг Водоснабжения:")
        for r in water_correct:
            if r['confidence']:
                print(f"   {r['query']:30s} → {r['confidence']:.3f} ✅")

        # Статистика
        avg_conf = sum(confidences) / len(confidences)
        below_09 = [c for c in confidences if c < 0.9]
        below_08 = [c for c in confidences if c < 0.8]

        print(f"\n Статистика:")
        print(f"   Средний confidence: {avg_conf:.3f}")
        print(f"   Ниже 0.9: {len(below_09)}/{len(confidences)} ({100*len(below_09)/len(confidences):.1f}%)")
        print(f"   Ниже 0.8: {len(below_08)}/{len(confidences)} ({100*len(below_08)/len(confidences):.1f}%)")

    print("\n" + "=" * 80)
    print("ВЫВОДЫ И РЕКОМЕНДАЦИИ")
    print("=" * 80)

    # Формируем выводы
    print("""
1. Если средний confidence для Водоснабжения < 0.9:
   → Порог 0.9 СЛИШКОМ ВЫСОКИЙ для Водоснабжения
   → РЕКОМЕНДАЦИЯ: Понизить до 0.8 для Водоснабжения

2. Если другие категории имеют confidence >= 0.9:
   → Порог 0.9 ПОДХОДИТ для остальных категорий
   → РЕКОМЕНДАЦИЯ: Исключение ТОЛЬКО для Водоснабжения

3. Если "нет * воды" имеют confidence ~0.8:
   → Это особенность запросов с "нет"
   → РЕКОМЕНДАЦИЯ: Спецправило для "нет" запросов
    """)

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(analyze_confidence_distribution())
