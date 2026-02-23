#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

import django
django.setup()

from llm_tester.models import PromptTemplate

prompt = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()

if prompt:
    old = prompt.template
    
    # Заменяем секцию ПРИМЕРЫ
    old_examples = """ ## ПРИМЕРЫ:
✅ "Где именно?" (2 слова)
✅ "Что именно сломалось?" (3 слова)
❌ "Это отопление или водоснабжение?" ("или")
❌ "Где и когда?" (двойной)"""
    
    new_examples = """ ## ПРИМЕРЫ:
✅ "Где именно?" (2 слова)
✅ "Что именно сломалось?" (3 слова)
❌ "Это отопление или водоснабжение?" ("или")
❌ "Где и когда?" (двойной)

## ПРИМЕРЫ ДЛЯ ВОДЫ (КРИТИЧЕСКИ ВАЖНО!):
ProblemText: "нет воды" → ✅ "Какой воды нет?" (НЕ "Какой воды слабый напор?")
ProblemText: "нет воды в квартире" → ✅ "Какой воды нет?" (НЕ "Уточните тип воды, напор которой слабый")
ProblemText: "пропала вода" → ✅ "Какой воды нет?"
❌ СМЕРТЕЛЬНО ПЛОХО: "Какой воды слабый напор?" (использует слова из услуги!)
❌ СМЕРТЕЛЬНО ПЛОХО: "Уточните тип воды, напор которой слабый" (использует слова из услуги!)"""
    
    if old_examples.strip() in old:
        new = old.replace(old_examples, new_examples)
        prompt.template = new
        prompt.save()
        print(f"✅ Промпт обновлен с примерами!")
        print(f"   Было: {len(old)}, стало: {len(new)} (+{len(new)-len(old)})")
    else:
        print("❌ Старые примеры не найдены")
        print("Ищем:", repr(old_examples[:100]))
        
