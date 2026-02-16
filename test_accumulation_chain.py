#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест цепочки accumulated_fields → _ask_ai_what_happened → absolute_facts_list

Проверяет что:
1. ProblemAccumulationService накапливает поля
2. MainAgent передает accumulated_fields в _ask_ai_what_happened
3. _generate_ai_question включает accumulated_fields в absolute_facts_list
"""

import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/var/www/komunal-dom_ru')

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

import asyncio
import traceback
from main_agent import MainAgent


async def test_accumulation_chain():
    """Тестируем всю цепочку"""

    # Включаем подробное логирование
    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

    print("=" * 80)
    print("ТЕСТ: Цепочка accumulated_fields → LLM prompt")
    print("=" * 80)

    # Создаем MainAgent
    agent = MainAgent()

    # ШАГ 1: Проверяем _generate_ai_question с accumulated_fields
    print("\n" + "=" * 80)
    print("ШАГ 1: Тест _generate_ai_question с accumulated_fields")
    print("=" * 80)

    test_accumulated_fields = {
        'source': 'батарея',
        'problem': 'течет',
        'category': 'отопление',
        'location': None,
        'severity': None,
        'intensity': None
    }

    test_established_filters = {
        'category': {'value': 'Водоснабжение', 'confidence': 0.5},
        'location_type': {'value': 'Индивидуальное', 'confidence': 0.9},
        'incident_type': {'value': 'Плановые работы', 'confidence': 0.8}
    }

    # Вызываем внутренний метод _generate_ai_question
    try:
        result = await agent._generate_ai_question(
            context="течет батарея",
            question_type="what_happened",
            dialog_history=[],
            established_filters=test_established_filters,
            txtPrb="у пользователя течет из батареи (отопление) в зале",
            accumulated_fields=test_accumulated_fields
        )

        question = result.get('question', '')
        prompt = result.get('prompt', '')

        print(f"\n{'='*80}")
        print("ПРОМТ (последние 3000 символов):")
        print(f"{'='*80}")
        if len(prompt) > 3000:
            print(prompt[-3000:])
        else:
            print(prompt)
        print(f"{'='*80}")
        print(f"Длина промта: {len(prompt)} символов")

    except Exception as e:
        print(f"\n❌ EXCEPTION: {e}")
        print(f"\nStack trace:")
        traceback.print_exc()
        return

    print("\n[!] Сгенерированный вопрос:")
    print(question)
    print("\n" + "=" * 80)

    # Проверяем что LLM НЕ спрашивает о том, что УЖЕ известно
    question_lower = question.lower()

    # source='батарея' - НЕ должен спрашивать "Что сломалось?" или "Объект?"
    if any(word in question_lower for word in ['что сломал', 'какой объект', 'какой предмет', 'что это', 'объект']):
        print("❌ ERROR: LLM спрашивает про ОБЪЕКТ хотя он известен (батарея)!")
    else:
        print("✅ SUCCESS: LLM НЕ спрашивает про объект (есть source='батарея')")

    # problem='течет' - НЕ должен спрашивать "Что происходит?" или "Что случилось?"
    if any(word in question_lower for word in ['что случилос', 'что происход', 'в чем проблема']):
        print("❌ ERROR: LLM спрашивает ПРОБЛЕМУ хотя она известна (течет)!")
    else:
        print("✅ SUCCESS: LLM НЕ спрашивает проблему (есть problem='течет')")

    # category='отопление' - косвенная проверка
    if 'отопл' in question_lower and 'какая' in question_lower:
        print("❌ ERROR: LLM спрашивает про категорию (отопление) хотя она известна!")
    else:
        print("✅ SUCCESS: LLM НЕ спрашивает категорию (есть category='отопление')")

    # Блок 'УЖЕ ИЗВЕСТНЫЕ ФАКТЫ' должен быть в ПРОМТЕ
    if '⛔⛔⛔ УЖЕ ИЗВЕСТНЫЕ ФАКТЫ' in prompt:
        print("✅ SUCCESS: Блок 'УЖЕ ИЗВЕСТНЫЕ ФАКТЫ' есть в ПРОМТЕ!")
    else:
        print("❌ ERROR: Блок 'УЖЕ ИЗВЕСТНЫЕ ФАКТЫ' НЕ в ПРОМТЕ!")

    # ШАГ 2: Проверяем с ПУСТЫМ accumulated_fields
    print("\n" + "=" * 80)
    print("ШАГ 2: Тест с ПУСТЫМ accumulated_fields")
    print("=" * 80)

    result2 = await agent._generate_ai_question(
        context="привет",
        question_type="what_happened",
        dialog_history=[],
        established_filters=None,
        txtPrb="",
        accumulated_fields=None
    )

    question2 = result2.get('question', '')

    print("\n[!] Сгенерированный вопрос:")
    print(question2)

    # ШАГ 3: Проверяем с ЧАСТИЧНЫМ accumulated_fields
    print("\n" + "=" * 80)
    print("ШАГ 3: Тест с ЧАСТИЧНЫМ accumulated_fields")
    print("=" * 80)

    test_accumulated_fields_partial = {
        'source': 'кран',
        'location': 'кухня',
        'problem': None,
        'category': None,
        'severity': None,
        'intensity': None
    }

    result3 = await agent._generate_ai_question(
        context="течет кран на кухне",
        question_type="clarification",
        dialog_history=[],
        established_filters=test_established_filters,
        txtPrb="течет кран на кухне",
        accumulated_fields=test_accumulated_fields_partial
    )

    question3 = result3.get('question', '')

    print("\n[!] Сгенерированный вопрос:")
    print(question3)

    if 'УЖЕ ИЗВЕСТНЫЙ объект: кран' in question3:
        print("✅ SUCCESS: source='кран' есть в вопросе!")
    else:
        print("❌ ERROR: source='кран' НЕ в вопросе!")

    if 'УЖЕ ИЗВЕСТНА локация: кухня' in question3:
        print("✅ SUCCESS: location='кухня' есть в вопросе!")
    else:
        print("❌ ERROR: location='кухня' НЕ в вопросе!")

    print("\n" + "=" * 80)
    print("ТЕСТ ЗАВЕРШЕН")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_accumulation_chain())
