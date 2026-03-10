#!/usr/bin/env python3
import sys, os
sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
import django
django.setup()
from llm_tester.models import PromptTemplate

prompt = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()
if prompt:
    # Финальная версия -_water type first!
    new_template = """# Помощник ЖКХ

## ПРАВИЛО ДЛЯ ВОДЫ:
Если {txtPrb} содержит "вод":
1. Сначала уточни ТИП (если не указан "горяч/холод")
2. ПОТОМ уточни локацию (если нужно)

Примеры:
- "нет вод" → "Какой воды — горячей или холодной?"
- "нет вод в кране" → "Какой воды — горячей или холодной?" (тип важнее!)
- "нет горячей воды" → "Где именно — в квартире или во всем доме?"

## В остальных случаях:
Один вопрос, 10 слов, без "или"

---
{txtPrb}
Уже известно: {absolute_facts}
Кандидаты: {candidates}

---
Вопрос:
"""
    
    prompt.template = new_template
    prompt.save()
    print(f"✅ ФИНАЛЬНАЯ версия (тип > локация)!")
    print(f"   Длина: {len(new_template)} символов")
    
