#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
import django
django.setup()
from llm_tester.models import PromptTemplate

prompt = PromptTemplate.objects.filter(slug='filter-location-type').first()
if prompt:
    # МАКСИМАЛЬНО простой промпт
    new_template = """## Роль
Классификатор локации. Строгий алгоритм, верни JSON.

## Вход
TXT_PRB = "{txtPrb}"

## АЛГОРИТМ (СТРОГО!)

### Шаг 1. Извлеки PLACE
PLACE = слова указывающие место (квартира, подъезд, двор и т.д.)

### Шаг 2. Классификация
location_type = null
confidence = 0.3

# Если ЯВНО указано "в квартире/в зале/в ванной" → Индивидуальное (1.0)
# Если ЯВНО указано "в подъезде/во дворе/на улице" → Общедомовое (1.0)
# Если НЕЯВНО (у меня/дома) или НЕ указано → null (0.3)

⛔ КРИТИЧЕСКИ ВАЖНО:
- "нет воды/света/тепла" БЕЗ места → null (0.3)
- "у меня" "дома" → НЕЯВНО → null (0.3)
- НЕ додумывай если нет явного указания!

### Шаг 3. JSON
{"location_type": [значение], "confidence": [значение], "reasoning": [логика]}
"""
    
    old_len = len(prompt.template)
    prompt.template = new_template
    prompt.save()
    
    print(f"✅ Промпт УПРОЩЕН!")
    print(f"   Было: {old_len} символов")
    print(f"   Стало: {len(new_template)} символов")
    print(f"   Сокращение: {old_len - len(new_template)} символов")
    
