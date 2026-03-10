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
    # Радикально - запретить локацию для воды!
    new_template = """# Помощник ЖКХ

⛔ ЗАПРЕТ: Если "вод" в проблеме - НЕ спрашивай локацию!
Только спрашивай ТИП воды: "Какой воды — горячей или холодной?"

Во всех остальных случаях:
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
    print(f"✅ ЗАПРЕТ локации для воды!")
    print(f"   Длина: {len(new_template)} символов")
    
