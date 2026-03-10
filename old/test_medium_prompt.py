#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
СБАЛАНСИРОВАННЫЙ промт (1000-1200 символов)
"""

import os
import sys
import django

sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

import asyncio
import json
from ai_agent_service import AIAgentService


def create_medium_prompt(txt_prb):
    """СБАЛАНСИРОВАННЫЙ промт (~1000 символов)"""
    return f"""## Роль
Классификатор категории проблемы. Верни JSON.

## Вход
TXT_PRB = "{txt_prb}"

## Категории и ключи (OBJ анализ)
1. Водоснабжение: вод, кран, смеситель, течет, протечк, капает, засор, труба
2. Электричество: электрич, свет, розетк, выключател, лампочк, не работает
3. Отопление: батарей, радиатор, отоплен, тепл, не греет, холодн
4. Канализация: канализ, унитаз, раковин, слив, туалет, засор
5. Газоснабжение: газ, плит, газов, запах газа, колонк
6. Лифты: лифт, кабин, застрял, не ездит
7. Вентиляция: вентиляци, вытяжк, духот, плох воздух
8. Конструктив: стен, потолок, пол, окн, двер, крыш, фасад, трещин
9. Санитария: мусор, уборк, гряз, насеком, грызун, таракан
10. Пожарная безопасность: пожар, alarm, огнетушит, датчик, эвакуац
11. Ремонт МАФ: дорожк, площадк, лавочк, асфальт, тротуар
12. Озеленение: дерев, куст, трав, газон, спил
13. Информационные запросы: вопрос, справк, документ, узнать, спрос

## EVENT коррекция
- Аварийные (прорв, течет, затоп, взрыв) → +0.3 к Водо/Канал/Газ/Отоп/Пожар
- Блокирующие (не работает, сломал) → +0.3 к Электр/Водо/Отоп
- Запросные (спрос, узнать) → +0.5 к Инфо-запрос

## PLACE коррекция
- Индивидуальное (кухн, ванн, зал) → +0.2 к Водо/Канал/Отоп/Электр
- Общедомовое (подъезд, лифт, подвал) → +0.3 к Лифт/Конструктив

## Алгоритм
1. Извлеки OBJ, EVENT, PLACE из TXT_PRB
2. Примени правила выше (OBJ*0.6 + EVENT*0.25 + PLACE*0.15)
3. Максимум. Если max < 0.7 → category=null

## Ответ
Верни ТОЛЬКО JSON: {{"category": "категория", "confidence": 0.7, "reasoning": "кратко"}}
"""


def parse_response(response_text):
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
    prompt = create_medium_prompt(txt_prb)
    
    try:
        response, usage = await agent.call_llm(
            prompt=prompt,
            provider='yandexgpt',
            model='lite',
            temperature=0.0,
            max_tokens=300
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
    print("=" * 100)
    print("ТЕСТИРОВАНИЕ СБАЛАНСИРОВАННОГО ПРОМПТА filter-category")
    print("=" * 100)
    
    agent = AIAgentService(provider='yandexgpt')
    
    test_cases = [
        ("течет батарея", "Отопление"),
        ("нет света", "Электричество"),
        ("запах газа", "Газоснабжение"),
        ("лифт застрял", "Лифты"),
        ("мусор не вывозят", "Санитария"),
        ("прорвало трубу", "Водоснабжение"),
        ("холодная батарея", "Отопление"),
        ("розетка не работает", "Электричество"),
        ("засор в унитазе", "Канализация"),
        ("трещина на стене", "Конструктив"),
        ("вода не течет", "Водоснабжение"),
        ("выключатель сломался", "Электричество"),
        ("подъемник не работает", "Лифты"),
        ("дерево упало", "Озеленение"),
        ("плохая вентиляция", "Вентиляция")
    ]
    
    results = []
    total_cost = 0
    
    for txt_prb, expected_category in test_cases:
        result = await test_single_prompt(agent, txt_prb)
        
        if 'error' in result:
            print(f"❌ {txt_prb:30s} | ERROR")
            results.append({'test': txt_prb, 'error': result['error']})
            continue
        
        actual_category = result.get('category')
        tokens = result.get('tokens', 0)
        cost = result.get('cost', 0)
        total_cost += cost
        
        match = actual_category == expected_category
        status = "✅" if match else "❌"
        
        print(f"{status} {txt_prb:30s} | {actual_category:20s} | {tokens:4d} токенов | {cost:.4f} руб")
        
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
    avg_tokens = sum(r.get('tokens', 0) for r in results) / total
    
    print(f"\n{'=' * 100}")
    print(f"Совпадений: {matches}/{total} ({matches/total*100:.1f}%)")
    print(f"Средние токены: {avg_tokens:.0f} (экономия {(1-avg_tokens/2243)*100:.0f}%)")
    print(f"Средняя стоимость: {total_cost/total:.4f} руб")
    
    prompt_len = len(create_medium_prompt("test"))
    print(f"Длина промта: {prompt_len} символов (~{prompt_len/4:.0f} токенов)")
    
    if matches/total >= 0.9:
        print("✅ ПРОМТ ОТЛИЧНЫЙ")
    elif matches/total >= 0.8:
        print("⚠️  НУЖНА ДОРАБОТКА")
    else:
        print("❌ ПРОМТ ПЛОХОЙ")


if __name__ == "__main__":
    asyncio.run(main())
