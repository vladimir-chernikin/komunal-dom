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
    
    # Добавляем правило ПЕРЕД "## СПИСОК КАНДИДАТОВ:"
    rule = '''## ⛔ ПРАВИЛО ДЛЯ "НЕТ ВОДЫ":
Если ProblemText содержит "нет вод", "пропал вод" или похожее:
- ⛔⛔⛔ ИГНОРИРУЙ список {candidates} полностью!
- НЕ смотри на названия услуг типа "Слабый напор воды"
- Используй ТОЛЬКО ProblemText для вопроса
- Спроси: "Какой воды нет?" или "Уточните тип воды"
'''
    
    # Вставляем перед "## СПИСОК КАНДИДАТОВ:"
    if "## СПИСОК КАНДИДАТОВ:" in old:
        new = old.replace("## СПИСОК КАНДИДАТОВ:", rule + "## СПИСОК КАНДИДАТОВ:")
        prompt.template = new
        prompt.save()
        print(f"✅ Промпт обновлен (игнорируем кандидатов)!")
        print(f"   Было: {len(old)}, стало: {len(new)} (+{len(new)-len(old)})")
    else:
        print("❌ Метка не найдена")
        
