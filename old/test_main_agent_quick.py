#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Быстрое тестирование 3-х примеров
"""

import os
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
django.setup()

from ai_agent_service import AIAgentService
from llm_tester.models import PromptTemplate

async def test_examples():
    # Загружаем промт
    tmpl = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()

    examples = [
        {
            "name": "Запах газа (Safety)",
            "message": "Пахнет газом в квартире, что делать?",
            "context": "",
            "expected": "Safety-инструкции + вопрос"
        },
        {
            "name": "Агрессия",
            "message": "Вы опять ничего не делаете! Я уже неделю жду!",
            "context": "",
            "expected": "Эмпатия + контроль + вопрос"
        },
        {
            "name": "Не работает лифт",
            "message": "Лифт не работает, застрял между этажами",
            "context": "",
            "expected": "Уточнение локации/срочности"
        }
    ]

    ai_service = AIAgentService()

    for i, ex in enumerate(examples, 1):
        print(f"\n{'='*80}")
        print(f"[{i}/{len(examples)}] {ex['name']}")
        print(f"{'='*80}")
        print(f"📥 СООБЩЕНИЕ: {ex['message']}")
        print(f"📋 ОЖИДАЕТСЯ: {ex['expected']}")

        # Формируем переменные
        variables = {
            'message_text': ex['message'],
            'context': ex['context'],
            'txtPrb': '{}',
            'established_filters_json': '{}',
            'KNOWLEDGE_BASE': '',
            'SERVICE_CATALOG': '- #Сантехника #Водоснабжение #Канализация #Отопление #Батарея #Радиатор\n- #Электроснабжение #Электрика #Свет\n- #Газоснабжение #Газ #Плита\n- #Лифт #Мусоропровод #Домофон\n- #Окна #Двери #Балкон #Лоджия\n- #Кровля #Фасад #Крыша\n- #Двор #Детская #Площадка #Парковка\n- #Подвал #Подпол\n- #Кондиционер #Сплит-система\n- #Прочее'
        }

        # Форматируем
        prompt = tmpl.template
        for key, value in variables.items():
            placeholder = f'{{{{{key}}}}}'
            prompt = prompt.replace(placeholder, str(value))

        # Вызываем AI
        try:
            response, usage = await ai_service.call_llm(
                prompt=prompt,
                provider="yandexgpt",
                temperature=0.3,
                max_tokens=500
            )

            print(f"\n✅ ОТВЕТ AI:")
            print("-"*80)
            print(response)
            print("-"*80)

            # Анализ
            question_count = response.count('?')
            words = response.split()
            print(f"\n🔊 АНАЛИЗ:")
            print(f"   - Вопросов: {question_count}")
            print(f"   - Длина: {len(words)} слов")
            print(f"   - Стоимость: {usage.get('cost_rub', 0):.4f} руб.")

        except Exception as e:
            print(f"\n❌ ОШИБКА: {e}")

asyncio.run(test_examples())
