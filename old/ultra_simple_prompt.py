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
    # УЛЬТРА-простой промпт - минимум текста, максимум ясности
    new_template = """# Помощник ЖКХ

## Если "нет вод":
Спроси: "Какой воды нет?" (не "горячей или холодной", не "слабый напор")

## В остальных случаях:
Один вопрос, 10 слов, без "или"

---
Проблема: {txtPrb}
Известно: {absolute_facts}
Кандидаты: {candidates}

Вопрос:
"""
    
    prompt.template = new_template
    prompt.save()
    
    print(f"✅ УЛЬТРА-простой промпт!")
    print(f"   Длина: {len(new_template)} символов")
    
