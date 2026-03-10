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
    # Финальный промпт - акцент на txtPrb
    new_template = """# MAIN AGENT — Помощник по ЖКХ

## ПРАВИЛО ДЛЯ ВОДЫ:
ЕСЛИ в {txtPrb} есть "нет вод" или "пропал вод":
- ✅ Спроси: "Какой воды нет?" или "Уточните тип воды"
- ❌ НЕ смотри на {candidates}! Используй только {txtPrb}
- ❌ НЕ пиши: "слабый напор", "переток" (это из названия услуги)

## ОБЩИЕ ПРАВИЛА:
- ОДИН вопрос, 10 слов, открытый
- Без "или", без перечислений  
- Не спрашивай уже известное из {absolute_facts}

---

{txtPrb}

Уже известно: {absolute_facts}
История: {dialog_history}

Кандидаты: {candidates}

---
Вопрос:
"""
    
    prompt.template = new_template
    prompt.save()
    
    print(f"✅ ФИНАЛЬНЫЙ промпт!")
    print(f"   Длина: {len(new_template)} символов")
    print(f"   Акцент на: txtPrb (НЕ candidates для воды)")
    
