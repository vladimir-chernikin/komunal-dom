#!/usr/bin/env python3
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
    
    # Точная замена с правильными переводами строк
    old_fragment = '❌ "Где и когда?" (двойной)\n\n---'
    new_fragment = '''❌ "Где и когда?" (двойной)

## ПРИМЕРЫ ДЛЯ ВОДЫ (КРИТИЧЕСКИ ВАЖНО!):
Если ProblemText содержит "нет вод" или "пропал вод":
- ✅ ПРАВИЛЬНО: "Какой воды нет?"
- ✅ ПРАВИЛЬНО: "Уточните тип воды"
- ❌ ЗАПРЕЩЕНО: "Какой воды слабый напор?" (НЕ используй слова из услуги!)
- ❌ ЗАПРЕЩЕНО: "Уточните тип воды, напор которой слабый"

---'''
    
    if old_fragment in old:
        new = old.replace(old_fragment, new_fragment)
        prompt.template = new
        prompt.save()
        print(f"✅ Промпт обновлен!")
        print(f"   Было: {len(old)}, стало: {len(new)} (+{len(new)-len(old)})")
    else:
        print("❌ Фрагмент не найден")
        print("Ищем:", repr(old_fragment))
        
