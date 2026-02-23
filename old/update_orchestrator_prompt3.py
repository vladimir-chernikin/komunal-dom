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

# Текущий промпт
prompt = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()

if not prompt:
    print("❌ Промпт не найден!")
else:
    old_template = prompt.template
    
    # Добавляем КРИТИЧЕСКОЕ правило в самое начало промпта (перед первым ## КРИТИЧЕСКИЕ ПРАВИЛА)
    critical_rule = """
## ⛔⛔⛔ СВЕРХКРИТИЧЕСКОЕ ПРАВИЛО ДЛЯ ВОДЫ ⛔⛔⛔
Если ProblemText содержит "нет вод":
- ЗАПРЕЩЕНО использовать слова "напор", "слабый", "переток" из названия услуги!
- ТОЛЬКО спрашивай: "Какой воды нет?" или "Уточните тип воды"
- ❌ ЗАПРЕЩЕНО: "Какой воды слабый напор?"
- ✅ РАЗРЕШЕНО: "Какой воды нет?"
"""
    
    # Вставляем после первого комментария
    if "# MAIN AGENT — Диалоговый ассистент для ЖКХ" in old_template:
        new_template = old_template.replace(
            "# MAIN AGENT — Диалоговый ассистент для ЖКХ                                         +",
            "# MAIN AGENT — Диалоговый ассистент для ЖКХ                                         +" + critical_rule
        )
        prompt.template = new_template
        prompt.save()
        
        print(f"✅ Промпт обновлен (радикальная версия)!")
        print(f"   Было: {len(old_template)} символов")
        print(f"   Стало: {len(new_template)} символов")
        print(f"   Добавлено: {len(new_template) - len(old_template)} символов")
    else:
        print("❌ Не найдена метка для вставки")

