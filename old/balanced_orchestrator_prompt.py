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
    # Балансированный промпт - минимум правил, максимум контекста
    new_template = """# MAIN AGENT — Помощник по ЖКХ

## ПРАВИЛО ДЛЯ ВОДЫ:
Если в проблеме есть "нет вод" / "пропал вод":
- Спроси: "Какой воды нет?" или "Уточните тип воды"
- ❌ НЕ используй слова из названия услуги ("слабый напор", "переток")
- ✅ Используй только ОПИСАНИЕ ПРОБЛЕМЫ от пользователя

## ОБЩИЕ ПРАВИЛА:
- ОДИН вопрос, 10 слов, открытый (Что? Как? Где?)
- Без "или", без перечислений
- Не спрашивай уже известное

---

## Проблема:
{txtPrb}

## Уже известно:
{absolute_facts}

## История:
{dialog_history}

## Кандидаты:
{candidates}

---
Задай ОДИН вопрос:
"""
    
    prompt.template = new_template
    prompt.save()
    
    print(f"✅ Промпт БАЛАНСИРОВАН!")
    print(f"   Длина: {len(new_template)} символов")
    print(f"   Правило для воды: ДА")
    print(f"   Контекст: txtPrb, absolute_facts, dialog_history, candidates")
    
