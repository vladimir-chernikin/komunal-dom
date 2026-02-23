#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

# Добавляем путь к проекту
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
    
    # Добавляем правило для Водоснабжения после "## ПРАВИЛО ДЛЯ УЖЕ ИЗВЕСТНЫХ ФАКТОВ:"
    rule_water = """
 ## ПРАВИЛО ДЛЯ ВОДОСНАБЖЕНИЯ (КРИТИЧЕСКИ ВАЖНО!):
 Если категория "Водоснабжение" (нет воды/слабый напор/протечка):
 - Проверь txtPrb: указан ли ТИП ("горячей", "холодной", "горячая", "холодная")?
 - Если тип НЕ указан:
   * Если location НЕ известен → спроси "Где именно нет воды?"
   * Если location УЖЕ известен → спроси "Какой воды нет?" или "Уточните тип воды"
   * ⛔ ЗАПРЕЩЕНО использовать слова из названия услуги!
   * ❌ ПЛОХО: "Какой воды слабый напор?"
   * ✅ ХОРОШО: "Какой воды нет?"
 - Если тип УЖЕ указан → НЕ спрашивай про тип, уточняй только неизвестное!
"""
    
    # Вставляем правило перед "## ВАЖНО:"
    if "## ВАЖНО:" in old_template:
        new_template = old_template.replace("## ВАЖНО:", rule_water + "\n## ВАЖНО:")
        prompt.template = new_template
        prompt.save()
        
        print(f"✅ Промпт обновлен!")
        print(f"   Было: {len(old_template)} символов")
        print(f"   Стало: {len(new_template)} символов")
        print(f"   Добавлено: {len(new_template) - len(old_template)} символов")
    else:
        print("❌ Не найдена метка '## ВАЖНО:' для вставки правила")

