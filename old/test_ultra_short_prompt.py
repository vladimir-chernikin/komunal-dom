#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестирование УЛЬТРА-КОРОТКОГО промта filter-category

Цель: сократить до 500-800 символов (100-200 токенов)
"""

import os
import sys
import django

# Настройка Django
sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

import asyncio
import json
from ai_agent_service import AIAgentService


def create_ultra_short_prompt(txt_prb):
    """УЛЬТРА-КОРОТКИЙ промт (500 символов)"""
    return f"""Классифицируй проблему "{txt_prb}" по категориям.

ВАРИАНТЫ:
Водоснабжение (вода, кран, труба, течет, засор)
Электричество (свет, розетка, выключатель, лампа)
Отопление (батарея, радиатор, холод, тепло)
Канализация (унитаз, раковина, слив, засор)
Газ (газ, плита, запах газа)
Лифт (лифт, кабина, застрял)
Вентиляция (вентиляция, вытяжка)
Конструктив (стена, потолок, пол, окно, дверь, трещина)
Санитария (мусор, грязь, уборка)
Пожарная безопасность (пожар, alarm, огнетушитель)
Ремонт МАФ (дорожка, площадка, лавочка, асфальт)
Озеленение (дерево, куст, трава, газон)
Инфо-запрос (вопрос, справка, документ, узнать)

Верни JSON: {{"category": "категория или null", "confidence": 0.7}}
"""


def parse_response(response_text):
    """Парсит JSON ответ"""
    try:
        response = response_text.strip()
        if response.startswith('```'):
            parts = response.split('```')
            response = parts[1] if len(parts) > 1 else response
        if response.startswith('json'):
            response = response[4:]
        return json.loads(response)
    except:
        return {'error': 'parse_error', 'raw': response_text[:100]}


async def test_single_prompt(agent, txt_prb):
    """Тестирует один промт"""
    prompt = create_ultra_short_prompt(txt_prb)
    
    try:
        response, usage = await agent.call_llm(
            prompt=prompt,
            provider='yandexgpt',
            model='lite',
            temperature=0.0,
            max_tokens=200
        )
        
        result = parse_response(response)
        result['tokens'] = usage.get('total_tokens', 0)
        result['cost'] = usage.get('cost_rub', 0)
        
        return result
    except Exception as e:
        return {
            'error': str(e),
            'category': None,
            'confidence': None
        }


async def main():
    """Тестирование"""
    
    print("=" * 100)
    print("ТЕСТИРОВАНИЕ УЛЬТРА-КОРОТКОГО ПРОМПТА filter-category")
    print("=" * 100)
    
    agent = AIAgentService(provider='yandexgpt')
    
    test_cases = [
        ("течет батарея", "Отопление"),
        ("нет света", "Электричество"),
        ("запах газа", "Газоснабжение"),
        ("лифт застрял", "Лифты"),
        ("мусор не вывозят", "Санитария"),
        ("прорвало трубу", "Водоснабжение"),
        ("розетка не работает", "Электричество"),
        ("засор в унитазе", "Канализация"),
        ("трещина на стене", "Конструктив"),
        ("плохая вентиляция", "Вентиляция")
    ]
    
    results = []
    total_cost = 0
    
    for txt_prb, expected_category in test_cases:
        result = await test_single_prompt(agent, txt_prb)
        
        if 'error' in result:
            print(f"❌ {txt_prb:30s} | ERROR: {result['error']}")
            results.append({'test': txt_prb, 'error': result['error']})
            continue
        
        actual_category = result.get('category')
        confidence = result.get('confidence')
        tokens = result.get('tokens', 0)
        cost = result.get('cost', 0)
        total_cost += cost
        
        match = actual_category == expected_category
        status = "✅" if match else "❌"
        
        print(f"{status} {txt_prb:30s} | {actual_category:20s} | Токены: {tokens:4d} | {cost:.4f} руб")
        
        results.append({
            'test': txt_prb,
            'expected': expected_category,
            'actual': actual_category,
            'match': match,
            'tokens': tokens,
            'cost': cost
        })
    
    # Итоги
    matches = sum(1 for r in results if r.get('match', False))
    total = len(results)
    errors = sum(1 for r in results if 'error' in r)
    
    avg_tokens = sum(r.get('tokens', 0) for r in results if 'tokens' in r) / max(total - errors, 1)
    
    print(f"\n{'=' * 100}")
    print(f"Всего: {total} | Совпадений: {matches}/{total} ({matches/total*100:.1f}%)")
    print(f"Средние токены: {avg_tokens:.0f} (было 2243, экономия {(1-avg_tokens/2243)*100:.0f}%)")
    print(f"Средняя стоимость: {total_cost/total:.4f} руб (было 0.7-0.8 руб)")
    
    # Длина промта
    prompt_len = len(create_ultra_short_prompt("test"))
    print(f"\nДлина промта: {prompt_len} символов (~{prompt_len/4:.0f} токенов)")
    
    match_pct = matches / total * 100
    if match_pct >= 90:
        print("✅ ПРОМТ ОТЛИЧНЫЙ")
    elif match_pct >= 80:
        print("⚠️  НУЖНА ДОРАБОТКА")
    else:
        print("❌ ПРОМТ ПЛОХОЙ")


if __name__ == "__main__":
    asyncio.run(main())
