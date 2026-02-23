#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тест 7 сценариев от 16 февраля
БЕЗОПАСНЫЙ: не меняет систему, только тестирует
"""

import os
import sys
import os
import django
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
django.setup()

from main_agent import MainAgent
from problem_accumulation_service import ProblemAccumulationService
from ai_agent_service import AIAgentService

# 7 сценариев из теста 16 февраля
SCENARIOS = [
    {
        "name": "1. Запах газа (safety)",
        "messages": ["привет", "у меня запах газа в квартире"],
        "expected": "safety-check (эвакуация + 104)"
    },
    {
        "name": "2. Агрессивный пользователь (negative)",
        "messages": ["опять ничего не делаете", "уже неделю жду"],
        "expected": "NEGATIVE mode (эмпатия + контроль)"
    },
    {
        "name": "3. Не работает лифт (triage)",
        "messages": ["лифт не работает"],
        "expected": "triage (уточнение этаж/дом)"
    },
    {
        "name": "4. Прорыв трубы (sanitary emergency)",
        "messages": ["у меня прорвало трубу", "в квартире"],
        "expected": "определение услуги (сантехника)"
    },
    {
        "name": "5. Холодная батарея (heating)",
        "messages": ["батарея холодная"],
        "expected": "определение услуги (отопление)"
    },
    {
        "name": "6. Фонарь во дворе (common area)",
        "messages": ["не горит фонарь во дворе"],
        "expected": "определение услуги (общедомовое)"
    },
    {
        "name": "7. Приветствие (chat)",
        "messages": ["привет", "здравствуйте"],
        "expected": "CHAT (ответ + вопрос)"
    },
]

async def test_scenario(scenario, main_agent, problem_service):
    """Тест одного сценария"""
    print(f"\n{'='*60}")
    print(f"СЦЕНАРИЙ: {scenario['name']}")
    print(f"ОЖИДАЕТСЯ: {scenario['expected']}")
    print('='*60)
    
    session_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    channel = "test"
    user_id = "test_user"
    
    results = {
        "messages": [],
        "total_cost": 0,
        "question_count": 0,
        "errors": []
    }
    
    try:
        for i, message in enumerate(scenario['messages'], 1):
            print(f"\n--- Сообщение {i}: '{message}' ---")
            
            # Накопление проблемы
            await problem_service.accumulate(session_id, message, channel)
            txtPrb = await problem_service.get_summary(session_id)
            
            # Вызов MainAgent
            response_data = await main_agent.process_message(
                message_text=message,
                session_id=session_id,
                channel=channel,
                user_id=user_id,
                txtPrb=txtPrb
            )
            
            # Результаты
            response_text = response_data.get('response', 'NO RESPONSE')
            cost = response_data.get('cost', 0)
            is_question = response_data.get('is_question', False)
            
            print(f"📨 Ответ: {response_text[:200]}")
            print(f"💰 Стоимость: {cost:.3f} руб")
            print(f"❓ Вопрос: {'ДА' if is_question else 'НЕТ'}")
            
            results['messages'].append({
                'input': message,
                'output': response_text,
                'cost': cost,
                'is_question': is_question
            })
            results['total_cost'] += cost
            if is_question:
                results['question_count'] += 1
            
    except Exception as e:
        error_msg = f"ОШИБКА: {str(e)}"
        print(f"\n❌ {error_msg}")
        results['errors'].append(error_msg)
    
    return results

async def main():
    """Главная функция"""
    print("="*60)
    print("ТЕСТ 7 СЦЕНАРИЕВ (16 февраля vs сейчас)")
    print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    # Инициализация сервисов (ОДИН РАЗ для всех сценариев)
    ai_agent = AIAgentService()
    main_agent = MainAgent()
    problem_service = ProblemAccumulationService(ai_agent)
    
    all_results = []
    total_cost = 0
    total_questions = 0
    
    for scenario in SCENARIOS:
        result = await test_scenario(scenario, main_agent, problem_service)
        result['name'] = scenario['name']
        result['expected'] = scenario['expected']
        all_results.append(result)
        total_cost += result['total_cost']
        total_questions += result['question_count']
    
    # Итоги
    print(f"\n\n{'='*60}")
    print("ИТОГИ ТЕСТА")
    print('='*60)
    print(f"Всего сценариев: {len(SCENARIOS)}")
    print(f"Общая стоимость: {total_cost:.3f} руб")
    print(f"Средняя стоимость: {total_cost/len(SCENARIOS):.3f} руб/сценарий")
    print(f"Всего вопросов: {total_questions}")
    print(f"Средних вопросов: {total_questions/len(SCENARIOS):.1f}/сценарий")
    
    # Сравнение с 16 февраля
    print(f"\n{'='*60}")
    print("СРАВНЕНИЕ С 16 ФЕВРАЛЯ")
    print('='*60)
    print(f"Стоимость 16 февраля: ~0.155 руб/запрос")
    print(f"Стоимость сейчас: {total_cost/len(SCENARIOS):.3f} руб/сценарий")
    if total_cost > 0:
        print(f"Разница: {((total_cost/len(SCENARIOS))/0.155 - 1)*100:+.1f}%")
    
    # Сохранение результатов
    output_file = f"/tmp/test_7_scenarios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"ТЕСТ 7 СЦЕНАРИЕВ\n")
        f.write(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"\nИТОГИ:\n")
        f.write(f"Общая стоимость: {total_cost:.3f} руб\n")
        f.write(f"Средняя стоимость: {total_cost/len(SCENARIOS):.3f} руб/сценарий\n")
        f.write(f"Всего вопросов: {total_questions}\n")
        f.write(f"\nСРАВНЕНИЕ:\n")
        f.write(f"16 февраля: ~0.155 руб/запрос\n")
        f.write(f"Сейчас: {total_cost/len(SCENARIOS):.3f} руб/сценарий\n")
        if total_cost > 0:
            f.write(f"Разница: {((total_cost/len(SCENARIOS))/0.155 - 1)*100:+.1f}%\n")
    
    print(f"\n📄 Результаты сохранены: {output_file}")
    print(f"\n✅ ТЕСТ ЗАВЕРШЕН (система не изменена)")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
