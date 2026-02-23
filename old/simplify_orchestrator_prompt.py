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
    old_len = len(prompt.template)
    
    # Новый минималистичный промпт
    new_template = """# MAIN AGENT — Помощник по ЖКХ

## ПРАВИЛО (ОДНО):
Если пользователь говорит "нет воды" / "пропала вода":
- Спроси: "Какой воды — горячей или холодной?"
- Примеры: 
  ✅ "Какой воды нет?"
  ✅ "Уточните — горячей или холодной?"
  
Во всех остальных случаях:
- Задай ОДИН вопрос для уточнения
- Максимум 10 слов
- Без "или", без перечислений

---

## Контекст:
Проблема: {txtPrb}
Известно: {absolute_facts}

---

## Кандидаты услуг:
{candidates}

---
Задай ОДИН вопрос:
"""
    
    prompt.template = new_template
    prompt.save()
    
    print(f"✅ Промпт УПРОЩЕН!")
    print(f"   Было: {old_len} символов")
    print(f"   Стало: {len(new_template)} символов")
    print(f"   Сокращение: {old_len - len(new_template)} символов ({100*(old_len - len(new_template))/old_len:.1f}%)")
    
