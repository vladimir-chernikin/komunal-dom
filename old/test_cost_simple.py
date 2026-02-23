#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import django
import asyncio
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from ai_agent_service import AIAgentService

# 7 простых тестов
TESTS = [
    "запах газа в квартире",
    "опять ничего не делаете",
    "лифт не работает",
    "прорвало трубу",
    "батарея холодная",
    "фонарь не горит",
    "здравствуйте"
]

async def main():
    ai_service = AIAgentService()
    
    print("="*60)
    print("ТЕСТ СТОИМОСТИ (7 запросов)")
    print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("="*60)
    
    total_cost = 0
    results = []
    
    for i, test in enumerate(TESTS, 1):
        try:
            print(f"\n{i}. {test[:40]}")
            
            # Простой вызов LLM
            response = await ai_service.generate(
                prompt=test,
                temperature=0.3
            )
            
            cost = response.get('cost', 0)
            total_cost += cost
            
            print(f"   💰 {cost:.3f} руб")
            results.append(cost)
            
        except Exception as e:
            print(f"   ❌ Ошибка: {str(e)[:50]}")
    
    # Итоги
    print(f"\n{'='*60}")
    print("ИТОГИ")
    print('='*60)
    print(f"Всего запросов: {len(results)}")
    print(f"Общая стоимость: {total_cost:.3f} руб")
    
    if results:
        avg_cost = total_cost / len(results)
        print(f"Средняя стоимость: {avg_cost:.3f} руб/запрос")
        
        print(f"\n{'='*60}")
        print("СРАВНЕНИЕ С 16 ФЕВРАЛЯ")
        print('='*60)
        print(f"16 февраля: ~0.155 руб/запрос")
        print(f"Сейчас: {avg_cost:.3f} руб/запрос")
        
        diff = (avg_cost / 0.155 - 1) * 100
        print(f"Разница: {diff:+.1f}%")
        
        if diff > 50:
            print(f"\n⚠️ ВЫВОД: СТОИМОСТЬ ВЫШЕ на {diff:.0f}%")
        elif diff < -20:
            print(f"\n✅ ВЫВОД: СТОИМОСТЬ НИЖЕ на {abs(diff):.0f}%")
        else:
            print(f"\n➡️ ВЫВОД: СТОИМОСТЬ СОПОСТАВИМА")

if __name__ == '__main__':
    asyncio.run(main())
