#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестирование оптимизированного промта filter-category

Сравнивает СТАРЫЙ и НОВЫЙ промты на реальных данных
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


def create_new_prompt(txt_prb):
    """Создает промт с подставленным txtPrb"""
    return f"""## Роль
Классификатор категории. Выполняй алгоритм. Верни JSON.

## Вход
TXT_PRB = "{txt_prb}"

## АЛГОРИТМ

### Шаг1. Извлеки OBJ, EVENT, PLACE из TXT_PRB

### Шаг2. Анализ OBJ (добавь категорию+вес)
- Водоснабжение: вод, кран, смеситель, течет, протечк, капает, засор → +0.7
- Электричество: электрич, свет, розетк, выключател, лампочк, не работает → +0.7
- Отопление: батарей, радиатор, отоплен, тепл, не греет, холодн → +0.7
- Канализация: канализ, унитаз, раковин, слив, туалет, засор → +0.7
- Газоснабжение: газ, плит, газов, колонк → +0.8
- Лифты: лифт, кабин, застрял, не ездит → +0.9
- Вентиляция: вентиляци, вытяжк, духот, плох воздух → +0.6
- Конструктив: стен, потолок, пол, окн, двер, крыш, фасад, трещин → +0.7
- Санитария: мусор, уборк, гряз, насеком, грызун, таракан → +0.7
- Пожарная безопасность: пожар, alarm, огнетушит, датчик, эвакуац → +0.8
- Ремонт МАФ: дорожк, площадк, лавочк, асфальт, тротуар → +0.6
- Озеленение: дерев, куст, трав, газон, спил → +0.7
- Информационные запросы: вопрос, справк, документ, узнать, спрос → +0.5

### Шаг3. Коррекция по EVENT
- Аварийные (прорв, течет, затоп, взрыв, пожар) → +0.3 к Водо/Канал/Газ/Отоп/Пожар
- Блокирующие (не работает, отключил, сломал) → +0.3 к Электр/Водо/Отоп
- Запросные (спрос, узнать, как, справк) → +0.5 к Инфо-запрос

### Шаг4. Коррекция по PLACE
- Индивидуальное (кухн, ванн, зал, спальн, балкон) → +0.2 к Водо/Канал/Отоп/Электр
- Общедомовое (подъезд, лифт, подвал, двор) → +0.3 к Лифт/Конструктив/Пожар

### Шаг5. Итог
Формула: OBJ*0.6 + EVENT*0.25 + PLACE*0.15
Максимум. Если max < 0.7 → category=null

### Шаг6. JSON
Верни: {{"category": "значение", "confidence": 0.7, "reasoning": "кратко"}}
"""


def parse_response(response_text):
    """Парсит JSON ответ"""
    try:
        # Удаляем markdown если есть
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
    prompt = create_new_prompt(txt_prb)
    
    try:
        response, usage = await agent.call_llm(
            prompt=prompt,
            provider='yandexgpt',
            model='lite',
            temperature=0.0,
            max_tokens=500
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
    """Тестирование на реальных данных"""
    
    print("=" * 100)
    print("ТЕСТИРОВАНИЕ ОПТИМИЗИРОВАННОГО ПРОМПТА filter-category")
    print("=" * 100)
    
    agent = AIAgentService(provider='yandexgpt')
    
    # Тестовые примеры (реальные из истории)
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
        print(f"\n{'─' * 100}")
        print(f"ТЕСТ: {txt_prb:30s} | ОЖИДАЕТСЯ: {expected_category}")
        print(f"{'─' * 100}")
        
        result = await test_single_prompt(agent, txt_prb)
        
        if 'error' in result:
            print(f"❌ ОШИБКА: {result['error']}")
            results.append({'test': txt_prb, 'error': result['error']})
            continue
        
        actual_category = result.get('category')
        confidence = result.get('confidence')
        tokens = result.get('tokens', 0)
        cost = result.get('cost', 0)
        total_cost += cost
        
        # Сравнение с ожиданием
        match = actual_category == expected_category
        status = "✅" if match else "❌"
        
        print(f"{status} РЕЗУЛЬТАТ: {actual_category:20s} | Confidence: {confidence} | Токены: {tokens:4d} | Стоимость: {cost:.4f} руб")
        
        if not match:
            print(f"   ⚠️  Ожидалось: {expected_category}, получено: {actual_category}")
        
        results.append({
            'test': txt_prb,
            'expected': expected_category,
            'actual': actual_category,
            'match': match,
            'tokens': tokens,
            'cost': cost
        })
    
    # Итоги
    print(f"\n{'=' * 100}")
    print("ИТОГИ")
    print(f"{'=' * 100}")
    
    matches = sum(1 for r in results if r.get('match', False))
    total = len(results)
    errors = sum(1 for r in results if 'error' in r)
    
    avg_tokens = sum(r.get('tokens', 0) for r in results if 'tokens' in r) / max(total - errors, 1)
    
    print(f"Всего тестов: {total}")
    print(f"Совпадений: {matches} ({matches/total*100:.1f}%)")
    print(f"Ошибок: {errors}")
    print(f"Средние токены: {avg_tokens:.0f}")
    print(f"Общая стоимость: {total_cost:.4f} руб")
    print(f"Средняя стоимость: {total_cost/total:.4f} руб")
    
    print(f"\nДетально:")
    for r in results:
        if 'error' in r:
            print(f"❌ {r['test']:30s} | ERROR: {r['error']}")
        else:
            status = "✅" if r['match'] else "❌"
            print(f"{status} {r['test']:30s} | {r['expected']:15s} → {r['actual']:15s}")
    
    # Рекомендация
    match_pct = matches / total * 100
    print(f"\n{'=' * 100}")
    if match_pct >= 90:
        print("✅ ПРОМТ ГОТОВ К ПРИМЕНЕНИЮ (≥90% совпадений)")
    elif match_pct >= 80:
        print("⚠️  НУЖНА ДОРАБОТКА (80-89% совпадений)")
    else:
        print("❌ ПРОМТ НУЖДАЕТСЯ В СУЩЕСТВЕННОЙ ДОРАБОТКЕ (<80%)")
    print(f"{'=' * 100}")


if __name__ == "__main__":
    asyncio.run(main())
