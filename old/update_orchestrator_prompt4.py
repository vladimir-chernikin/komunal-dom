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
    old_template = prompt.template
    
    # Добавляем правило ПЕРЕД "## КРИТИЧЕСКИЕ ПРАВИЛА:"
    new_section = """
## ⛔⛔⛔ СВЕРХКРИТИЧЕСКОЕ ПРАВИЛО (если ProblemText содержит "нет вод"):
- ⛔ ЗАПРЕЩЕНО: "слабый напор", "переток", "протечка" из названия услуги!
- ✅ ТОЛЬКО: "Какой воды нет?" или "Уточните тип воды"

"""
    
    if "## КРИТИЧЕСКИЕ ПРАВИЛА:" in old_template:
        new_template = old_template.replace(
            " ## КРИТИЧЕСКИЕ ПРАВИЛА:",
            new_section + "## КРИТИЧЕСКИЕ ПРАВИЛА:"
        )
        prompt.template = new_template
        prompt.save()
        print(f"✅ Промпт обновлен!")
        print(f"   Было: {len(old_template)}, стало: {len(new_template)}")
    else:
        print("❌ Не найдена метка")
else:
    print("❌ Промпт не найден")

