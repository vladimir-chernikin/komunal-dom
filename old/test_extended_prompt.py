#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
РАСШИРЕННОЕ тестирование промта mainagent-orchestrator

20+ кейсов для проверки:
- Газ/пожар (опасность)
- Двойные вопросы
- Уже известные факты
- Множественные кандидаты
- Приветствия
- Негатив
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


async def test_extended():
    """Расширенное тестирование"""

    print("="*100)
    print("РАСШИРЕННОЕ ТЕСТИРОВАНИЕ ПРОМТА mainagent-orchestrator")
    print("="*100)

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

    agent = AIAgentService(provider='yandexgpt')

    # Расширенные тестовые кейсы
    test_cases = [
        {
            'name': '1. Газ (опасность!)',
            'vars': {
                'context': 'пахнет газом',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: запах газа',
                'txtPrb': 'пахнет газом',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 51, "Наименование": "Запах газа", "Фильтры": {"Тип": "Инцидент"}}]\n```'
            },
            'expect': 'question_about_location_or_instructions'
        },
        {
            'name': '2. Пожар (критическая опасность)',
            'vars': {
                'context': 'пожар в подъезде',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА локация: подъезд\n- УЖЕ ИЗВЕСТНА проблема: пожар',
                'txtPrb': 'пожар в подъезде',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 73, "Наименование": "Пожар общедомовой", "Фильтры": {"Тип": "Инцидент"}}]\n```'
            },
            'expect': 'urgent_instructions'
        },
        {
            'name': '3. Первое "течёт"',
            'vars': {
                'context': 'течёт',
                'absolute_facts': '(нет известных фактов)',
                'txtPrb': 'течёт',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 32, "Наименование": "Прорыв труб в квартире"}, {"КодУслуги": 33, "Наименование": "Общедомовой прорыв труб"}]\n```'
            },
            'expect': 'question_about_location'
        },
        {
            'name': '4. Известно: "течёт из батареи в зале"',
            'vars': {
                'context': 'течёт из батареи в зале',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: течёт из батареи\n- УЖЕ ИЗВЕСТНА локация: зал',
                'txtPrb': 'течёт из батареи в зале',
                'dialog_history': 'Пользователь: течёт\nБот: Где именно?\nПользователь: из батареи\nБот: Где?\nПользователь: в зале',
                'established_filters': '{"object_description": {"value": "течёт из батареи", "confidence": 0.9}, "location_type": {"value": "Индивидуальное", "confidence": 0.9}}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 31, "Наименование": "Протечка батареи/радиатора в квартире", "Фильтры": {"Тип": "Инцидент", "Категория": "Отопление"}}]\n```'
            },
            'expect': 'confirm_service'
        },
        {
            'name': '5. "сломалось" (нужен объект)',
            'vars': {
                'context': 'сломалось',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: сломалось',
                'txtPrb': 'сломалось',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 49}, {"КодУслуги": 50}, {"КодУслуги": 47}]\n```'
            },
            'expect': 'question_about_what'
        },
        {
            'name': '6. "нет света" (частично известно)',
            'vars': {
                'context': 'нет света',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: нет света',
                'txtPrb': 'нет света',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 43, "Наименование": "Нет света во всем доме"}, {"КодУслуги": 44, "Наименование": "Нет света в части дома"}, {"КодУслуги": 46, "Наименование": "Нет света индивидуальное"}]\n```'
            },
            'expect': 'question_about_scope'
        },
        {
            'name': '7. Приветствие',
            'vars': {
                'context': 'привет',
                'absolute_facts': '(нет известных фактов)',
                'txtPrb': 'привет',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': '(нет кандидатов)'
            },
            'expect': 'greeting_with_question'
        },
        {
            'name': '8. Негатив "опять всё сломалось"',
            'vars': {
                'context': 'опять всё сломалось',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: сломалось\n- УЖЕ ИЗВЕСТНО настроение: негатив',
                'txtPrb': 'опять всё сломалось',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': '[]'
            },
            'expect': 'empathy_with_question'
        },
        {
            'name': '9. "засорился унитаз"',
            'vars': {
                'context': 'засорился унитаз',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: засор\n- УЖЕ ИЗВЕСТНЫЙ объект: унитаз',
                'txtPrb': 'засорился унитаз',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 57, "Наименование": "Засор канализации индивидуальный", "Фильтры": {"Тип": "Инцидент", "Категория": "Канализация"}}]\n```'
            },
            'expect': 'confirm_or_details'
        },
        {
            'name': '10. "лифт не работает"',
            'vars': {
                'context': 'лифт не работает',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: лифт не работает\n- УЖЕ ИЗВЕСТНЫЙ объект: лифт',
                'txtPrb': 'лифт не работает',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 55, "Наименование": "Лифт не работает, двери застряли, люди внутри", "Фильтры": {"Тип": "Инцидент", "Категория": "Лифты"}}]\n```'
            },
            'expect': 'check_people_inside'
        },
        {
            'name': '11. "нет горячей воды"',
            'vars': {
                'context': 'нет горячей воды',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: нет горячей воды',
                'txtPrb': 'нет горячей воды',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 34, "Наименование": "Нет горячей воды во всём доме", "Фильтры": {"Тип": "Инцидент"}}]\n```'
            },
            'expect': 'confirm_service_or_check_duration'
        },
        {
            'name': '12. Множество кандидатов (3 категории)',
            'vars': {
                'context': 'не работает',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: не работает',
                'txtPrb': 'не работает',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 47, "Наименование": "Не работает домофон"}, {"КодУслуги": 46, "Наименование": "Нет света индивидуальное"}, {"КодУслуги": 55, "Наименование": "Лифт не работает"}]\n```'
            },
            'expect': 'question_about_what_object'
        },
        {
            'name': '13. Известно всё - подтверждение',
            'vars': {
                'context': 'прорвало трубу холодной воды на кухне',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: прорыв трубы\n- УЖЕ ИЗВЕСТНЫЙ объект: труба холодной воды\n- УЖЕ ИЗВЕСТНА локация: кухня',
                'txtPrb': 'прорвало трубу холодной воды на кухне',
                'dialog_history': 'Пользователь: прорвало\nБот: Что именно?\nПользователь: трубу холодной воды\nБот: Где?\nПользователь: на кухне',
                'established_filters': '{"category": {"value": "Водоснабжение", "confidence": 0.95}}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 32, "Наименование": "Прорыв труб в квартире", "Фильтры": {"Тип": "Инцидент", "Категория": "Водоснабжение"}}]\n```'
            },
            'expect': 'confirm_service'
        },
        {
            'name': '14. Затопление от соседей',
            'vars': {
                'context': 'заливают соседи сверху',
                'absolute_facts': '- УЖЕ ИЗВЕСТНА проблема: затопление\n- УЖЕ ИЗВЕСТНЫЙ источник: соседи сверху',
                'txtPrb': 'заливают соседи сверху',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 35, "Наименование": "Затопление от соседей", "Фильтры": {"Тип": "Инцидент", "Категория": "Водоснабжение"}}]\n```'
            },
            'expect': 'confirm_or_ask_which_room'
        },
        {
            'name': '15. Запрос информации',
            'vars': {
                'context': 'хочу узнать свой баланс',
                'absolute_facts': '- УЖЕ ИЗВЕСТНЫЙ тип запроса: информационный',
                'txtPrb': 'хочу узнать свой баланс',
                'dialog_history': '(история пуста)',
                'established_filters': '{}',
                'candidates': 'СПИСОК КАНДИДАТОВ:\n```json\n[{"КодУслуги": 66, "Наименование": "Лицевые счета присвоение"}, {"КодУслуги": 72, "Наименование": "Запросы по квартирным платежам"}]\n```'
            },
            'expect': 'redirect_or_ask_for_details'
        }
    ]

    results = []
    total_cost = 0

    for i, case in enumerate(test_cases, 1):
        print(f"\n{'='*100}")
        print(f"ТЕСТ {i}/{len(test_cases)}: {case['name']}")
        print(f"Ожидается: {case['expect']}")
        print(f"{'='*100}")

        try:
            prompt = prompt_template.format(**case['vars'])
        except KeyError as e:
            print(f"❌ ОШИБКА формата: {e}")
            continue

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
            print(f"\n📊 Токены: {tokens} | Стоимость: {cost:.4f} руб")

            # Анализ качества
            issues = []

            if any(marker in response for marker in ['MODE:', 'txtPrb', 'JSON', 'КодУслуги']):
                issues.append("Есть метаданные")

            if ' или ' in response.lower():
                issues.append('Использовано "или"')

            if response.count('?') > 1:
                issues.append("Более одного вопроса")

            questions = [q.strip() for q in response.split('?') if q.strip()]
            if questions:
                last_q = questions[0]
                words = last_q.split()
                if len(words) > 10:
                    issues.append(f"Вопрос {len(words)} слов (>10)")

            # Проверка закрытых вопросов
            closed = ['да или нет', 'правильно ли', 'верно ли', 'это да']
            if any(p in response.lower() for p in closed):
                issues.append("Закрытый вопрос")

            status = 'OK' if not issues else 'ISSUES'
            for issue in issues:
                print(f"   ⚠️  {issue}")

            results.append({
                'test': case['name'],
                'response': response,
                'tokens': tokens,
                'cost': cost,
                'status': status,
                'issues': issues
            })

        except Exception as e:
            print(f"\n❌ Ошибка: {e}")
            results.append({'test': case['name'], 'status': 'ERROR', 'error': str(e)})

    # Итоги
    print(f"\n\n{'='*100}")
    print("ИТОГИ РАСШИРЕННОГО ТЕСТИРОВАНИЯ")
    print(f"{'='*100}")

    ok = sum(1 for r in results if r['status'] == 'OK')
    issues = sum(1 for r in results if r['status'] == 'ISSUES')
    errors = sum(1 for r in results if r['status'] == 'ERROR')

    print(f"Всего тестов: {len(results)}")
    print(f"✅ OK: {ok}")
    print(f"⚠️  С проблемами: {issues}")
    print(f"❌ Ошибки: {errors}")
    print(f"💰 Стоимость: {total_cost:.4f} руб (средне: {total_cost/len(results):.4f} руб/тест)")

    if ok == len(results):
        print("\n✅ ПРОМТ ОТЛИЧНЫЙ - ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    elif ok >= len(results) * 0.8:
        print("\n⚠️  ПРОМТ ХОРОШИЙ - большинство тестов пройдено")
    else:
        print("\n❌ ПРОМТ ТРЕБУЕТ ДОРАБОТКИ")

    # Детальные проблемы
    if issues > 0:
        print(f"\n⚠️  ПРОБЛЕМНЫЕ ТЕСТЫ:")
        for r in results:
            if r['status'] == 'ISSUES':
                print(f"   • {r['test']}")
                for issue in r.get('issues', []):
                    print(f"      - {issue}")

    print(f"{'='*100}\n")


if __name__ == "__main__":
    asyncio.run(test_extended())
