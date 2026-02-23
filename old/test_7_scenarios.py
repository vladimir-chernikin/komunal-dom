#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import django
from datetime import datetime
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from main_agent import MainAgent

SCENARIOS = [
    {"name": "1. Газ (safety)", "messages": ["запах газа"], "expected": "safety"},
    {"name": "2. Агрессия (negative)", "messages": ["опять ничего не делаете"], "expected": "negative"},
    {"name": "3. Лифт (triage)", "messages": ["лифт не работает"], "expected": "triage"},
    {"name": "4. Труба (water)", "messages": ["прорвало трубу"], "expected": "water"},
    {"name": "5. Батарея (heating)", "messages": ["батарея холодная"], "expected": "heating"},
    {"name": "6. Фонарь (common)", "messages": ["фонарь не горит"], "expected": "common"},
    {"name": "7. Привет (chat)", "messages": ["здравствуйте"], "expected": "chat"},
]

async def test_scenario(scenario, main_agent, idx):
    print(f"\n{'='*50}")
    print(f"{scenario['name']}: {scenario['messages'][0]}")
    print('='*50)
    
    try:
        response = await main_agent.process_message(
            message_text=scenario['messages'][0],
            session_id=f"test_{idx}",
            channel="test",
            user_id="test"
        )
        
        text = response.get('response', '')[:150]
        cost = response.get('cost', 0)
        
        print(f"📨 {text}...")
        print(f"💰 {cost:.3f} руб")
        
        return {'cost': cost, 'success': True}
        
    except Exception as e:
        print(f"❌ Ошибка: {str(e)[:100]}")
        return {'cost': 0, 'success': False}

async def main():
    print("="*50)
    print("ТЕСТ 7 СЦЕНАРИЕВ")
    print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*50)
    
    main_agent = MainAgent()
    results = []
    
    for idx, scenario in enumerate(SCENARIOS):
        result = await test_scenario(scenario, main_agent, idx)
        result['name'] = scenario['name']
        results.append(result)
    
    # Итоги
    successful = [r for r in results if r['success']]
    total_cost = sum(r['cost'] for r in successful)
    
    print(f"\n{'='*50}")
    print("ИТОГИ")
    print('='*50)
    print(f"Успешных: {len(successful)}/{len(SCENARIOS)}")
    
    if successful:
        avg_cost = total_cost / len(successful)
        print(f"Общая стоимость: {total_cost:.3f} руб")
        print(f"Средняя стоимость: {avg_cost:.3f} руб/запрос")
        
        print(f"\n{'='*50}")
        print("СРАВНЕНИЕ С 16 ФЕВРАЛЯ")
        print('='*50)
        print(f"16 февраля: 0.155 руб/запрос")
        print(f"Сейчас: {avg_cost:.3f} руб/запрос")
        
        diff = (avg_cost / 0.155 - 1) * 100
        print(f"Разница: {diff:+.1f}%")
        
        if diff > 50:
            print(f"\n⚠️ СТОИМОСТЬ ВЫШЕ на {diff:.0f}%")
        elif diff < -20:
            print(f"\n✅ СТОИМОСТЬ НИЖЕ на {abs(diff):.0f}%")
        else:
            print(f"\n➡️ СТОИМОСТЬ СОПОСТАВИМА")

if __name__ == '__main__':
    asyncio.run(main())
