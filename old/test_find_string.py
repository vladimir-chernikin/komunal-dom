#!/usr/bin/env python3
import sys
sys.path.insert(0, '/var/www/komunal-dom_ru')
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
import django
django.setup()
from llm_tester.models import PromptTemplate

prompt = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()
if prompt:
    tmpl = prompt.template
    # Найти позицию "## ПРИМЕРЫ:"
    idx = tmpl.find("## ПРИМЕРЫ:")
    if idx != -1:
        print(f"Найдено на позиции {idx}")
        print("Фрагмент:")
        print(repr(tmpl[idx:idx+200]))
    else:
        print("НЕ найдено")
        
