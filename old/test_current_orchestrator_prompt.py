#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестирование ТЕКУЩЕГО СОКРАЩЁННОГО промта mainagent-orchestrator
"""

import os
import sys
import django
import asyncio
import json

sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from llm_tester.models import PromptTemplate
from ai_agent_service import AIAgentService
from asgiref.sync import sync_to_async


async def test_prompt():
    """Тестирует промт на нескольких кейсах"""

    print("="*100)
    print("ТЕСТИРОВАНИЕ ТЕКУЩЕГО ПРОМТА mainagent-orchestrator")
    print("="*100)

    # Загружаем промт через sync_to_async
    @sync_to_async
    def get_prompt():
        return PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()

    tmpl = await get_prompt()
    if not tmpl:
        print("❌ Промет не найден!")
        return

    prompt_template = tmpl.template
    print(f"\n✅ Промет загружен (ID: {tmpl.id})")
    print(f"📏 Длина: {len(prompt_template)} символов")
    print(f"\n📋 СОДЕРЖАНИЕ ПРОМТА:")
    print("-" * 100)
    print(prompt_template)
    print("-" * 100)

    agent = AIAgentService(provider='yandexgpt')

    # Тестовые кейсы
    test_cases = [
        {
            'name': 'Кейс 1: "течёт" (первое сообщение)',
            'vars': {
                'context': 'течёт',
                'absolute_facts': '(нет известных фактов)',
                'txtPrb': 'течёт',
                'dialog_history': '(история пуста)',
                'established_filters': '(нет фильтров)',
                'candidates': '''СПИСОК КАНДИДАТОВ (услуги которые подходят под описание):
```json
[
  {"КодУслуги": 1, "Наименование": "Устранение протечки воды из труб отопления", "Фильтры": {"Тип": "Инцидент", "Вид": "Индивидуальное", "Категория": "Отопление", "Объект": "Труба"}},
  {"КодУслуги": 2, "Наименование": "Устранение протечки воды из труб водоснабжения", "Фильтры": {"Тип": "Инцидент", "Вид": "Индивидуальное", "Категория": "Водоснабжение", "Объект": "Труба"}}
]
```'''
            }
        },
        {
            'name': 'Кейс 2: "течёт из батареи в зале" (известен объект и локация)',
            'vars': {
                'context': 'течёт из батареи в зале',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: течёт из батареи\n- УЖЕ ИЗВЕСТНА локация: зал',
                'txtPrb': 'течёт из батареи в зале',
                'dialog_history': 'Пользователь: течёт\nБот: Что именно течёт?\nПользователь: из батареи\nБот: Где именно?\nПользователь: в зале',
                'established_filters': "{'object_description': {'value': 'течёт из батареи', 'confidence': 0.9}, 'location_type': {'value': 'Индивидуальное', 'confidence': 0.9}}",
                'candidates': '''СПИСОК КАНДИДАТОВ (услуги которые подходят под описание):
```json
[
  {"КодУслуги": 1, "Наименование": "Устранение протечки воды из труб отопления", "Фильтры": {"Тип": "Инцидент", "Вид": "Индивидуальное", "Категория": "Отопление", "Объект": "Батарея"}}
]
```'''
            }
        },
        {
            'name': 'Кейс 3: "пахнет газом" (опасность!)',
            'vars': {
                'context': 'пахнет газом на кухне',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА локация: кухня\n- УЖЕ ИЗВЕСТНА проблема: запах газа',
                'txtPrb': 'пахнет газом на кухне',
                'dialog_history': '(история пуста)',
                'established_filters': "{'location_type': {'value': 'Индивидуальное', 'confidence': 0.9}}",
                'candidates': '''СПИСОК КАНДИДАТОВ (услуги которые подходят под описание):
```json
[
  {"КодУслуги": 10, "Наименование": "Аварийная ситуация: утечка газа", "Фильтры": {"Тип": "Инцидент", "Вид": "Индивидуальное", "Категория": "Газоснабжение", "Объект": "Газовая труба"}}
]
```'''
            }
        },
        {
            'name': 'Кейс 4: "сломалось" (нужно уточнение)',
            'vars': {
                'context': 'сломалось',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: сломалось',
                'txtPrb': 'сломалось',
                'dialog_history': '(история пуста)',
                'established_filters': '(нет фильтров)',
                'candidates': '''СПИСОК КАНДИДАТОВ (услуги которые подходят под описание):
```json
[
  {"КодУслуги": 1, "Наименование": "Ремонт крана", "Фильтры": {"Тип": "Инцидент", "Категория": "Водоснабжение", "Объект": "Кран"}},
  {"КодУслуги": 2, "Наименование": "Ремонт розетки", "Фильтры": {"Тип": "Инцидент", "Категория": "Электрика", "Объект": "Розетка"}},
  {"КодУслуги": 3, "Наименование": "Ремонт лифта", "Фильтры": {"Тип": "Инцидент", "Категория": "Лифты", "Объект": "Лифт"}}
]
```'''
            }
        },
        {
            'name': 'Кейс 5: "привет" (приветствие)',
            'vars': {
                'context': 'привет',
                'absolute_facts': '(нет известных фактов)',
                'txtPrb': 'привет',
                'dialog_history': '(история пуста)',
                'established_filters': '(нет фильтров)',
                'candidates': '(нет кандидатов)'
            }
        }
    ]

    results = []
    total_cost = 0

    for i, case in enumerate(test_cases, 1):
        print(f"\n{'='*100}")
        print(f"ТЕСТ {i}/{len(test_cases)}: {case['name']}")
        print(f"{'='*100}")

        # Формируем промт
        try:
            prompt = prompt_template.format(**case['vars'])
        except KeyError as e:
            print(f"❌ ОШИБКА формата: отсутствует переменная {e}")
            continue

        print(f"📊 Входные данные:")
        print(f"   txtPrb: {case['vars']['txtPrb']}")
        print(f"   absolute_facts: {case['vars']['absolute_facts'][:50]}...")
        print(f"\n📝 Длина промта: {len(prompt)} символов")

        try:
            response, usage = await agent.call_llm(
                prompt=prompt,
                provider='yandexgpt',
                model='lite',
                temperature=0.0,
                max_tokens=300
            )

            tokens = usage.get('total_tokens', 0)
            cost = usage.get('cost_rub', 0)
            total_cost += cost

            print(f"\n🤖 ОТВЕТ LLM:")
            print(f"   {response}")
            print(f"\n📊 Метрики:")
            print(f"   Токены: {tokens}")
            print(f"   Стоимость: {cost:.4f} руб")

            # Проверка качества ответа
            issues = []

            # Проверка на метаданные
            if any(marker in response for marker in ['MODE:', 'txtPrb', 'JSON', 'этап воронки', 'КодУслуги']):
                issues.append("Есть внутренние метаданные")

            # Проверка на двойной вопрос
            if ' или ' in response.lower() or response.count('?') > 1:
                issues.append("Двойной вопрос или 'или'")

            # Проверка на закрытый вопрос
            closed_patterns = ['да или нет', 'правильно ли', 'верно ли']
            if any(pattern in response.lower() for pattern in closed_patterns):
                issues.append("Закрытый вопрос (да/нет)")

            # Проверка длины вопроса
            questions = [q.strip() for q in response.split('?') if q.strip()]
            if questions:
                last_question = questions[0]
                words = last_question.split()
                if len(words) > 10:
                    issues.append(f"Вопрос слишком длинный: {len(words)} слов")

            # Проверка на вопрос
            if '?' not in response and case['vars']['candidates'] != '(нет кандидатов)':
                issues.append("Нет вопроса (а должен быть)")

            if issues:
                print(f"\n⚠️ Проблемы:")
                for issue in issues:
                    print(f"   - {issue}")
                results.append({'status': 'ISSUES', 'test': case['name'], 'issues': issues})
            else:
                print(f"\n✅ Ответ корректный")
                results.append({'status': 'OK', 'test': case['name']})

        except Exception as e:
            print(f"\n❌ Ошибка LLM: {e}")
            results.append({'status': 'ERROR', 'test': case['name'], 'error': str(e)})

    # Итоги
    print(f"\n\n{'='*100}")
    print("ИТОГИ ТЕСТИРОВАНИЯ")
    print(f"{'='*100}")

    ok = sum(1 for r in results if r['status'] == 'OK')
    issues = sum(1 for r in results if r['status'] == 'ISSUES')
    errors = sum(1 for r in results if r['status'] == 'ERROR')

    print(f"Всего: {len(results)}")
    print(f"✅ OK: {ok}")
    print(f"⚠️  С проблемами: {issues}")
    print(f"❌ Ошибки: {errors}")
    print(f"💰 Стоимость: {total_cost:.4f} руб")

    if ok == len(results):
        print("\n✅ ПРОМТ ОТЛИЧНЫЙ!")
    elif ok >= len(results) * 0.7:
        print("\n⚠️  ПРОМТ ХОРОШИЙ, но есть замечания")
    else:
        print("\n❌ ПРОМТ ТРЕБУЕТ ДОРАБОТКИ!")

    print(f"{'='*100}\n")


if __name__ == "__main__":
    asyncio.run(test_prompt())
