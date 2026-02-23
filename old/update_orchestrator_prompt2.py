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
    
    # Заменяем старое правило на более жесткое
    old_rule = """ ## ПРАВИЛО ДЛЯ ВОДОСНАБЖЕНИЯ (КРИТИЧЕСКИ ВАЖНО!):
 Если категория "Водоснабжение" (нет воды/слабый напор/протечка):
 - Проверь txtPrb: указан ли ТИП ("горячей", "холодной", "горячая", "холодная")?
 - Если тип НЕ указан:
   * Если location НЕ известен → спроси "Где именно нет воды?"
   * Если location УЖЕ известен → спроси "Какой воды нет?" или "Уточните тип воды"
   * ⛔ ЗАПРЕЩЕНО использовать слова из названия услуги!
   * ❌ ПЛОХО: "Какой воды слабый напор?"
   * ✅ ХОРОШО: "Какой воды нет?"
 - Если тип УЖЕ указан → НЕ спрашивай про тип, уточняй только неизвестное!"""
    
    new_rule = """ ## ПРАВИЛО ДЛЯ ВОДОСНАБЖЕНИЯ (КРИТИЧЕСКИ ВАЖНО!):
 Если в ProblemText (txtPrb) есть "вод" и категория "Водоснабжение":
 - ⛔⛔⛔ ИГНОРИРУЙ названия услуг-кандидатов! Используй ТОЛЬКО ProblemText!
 - Проверь ProblemText: есть ли ТИП ("горячей", "холодной", "горячая", "холодная")?
 - Если тип НЕ указан:
   * Если location НЕ известен → спроси "Где именно нет воды?"
   * Если location УЖЕ известен → спроси "Какой воды нет?" или "Уточните тип воды"
   * ⛔⛔⛔ КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО использовать слова из названия услуги-кандидата!
   * ❌ СМЕРТЕЛЬНО ПЛОХО: "Какой воды слабый напор?" (использует слова из услуги "Слабый напор воды")
   * ❌ СМЕРТЕЛЬНО ПЛОХО: "Уточните тип воды, напор которой слабый"
   * ✅ ИДЕАЛЬНО: "Какой воды нет?" (использует ТОЛЬКО ProblemText "нет воды")
   * ✅ ИДЕАЛЬНО: "Уточните тип воды" (нейтральный вопрос БЕЗ слов из услуги)
 - Если тип УЖЕ указан в ProblemText → НЕ спрашивай про тип!"""
    
    if old_rule in old_template:
        new_template = old_template.replace(old_rule, new_rule)
        prompt.template = new_template
        prompt.save()
        
        print(f"✅ Промпт обновлен (жесткая версия)!")
        print(f"   Было: {len(old_template)} символов")
        print(f"   Стало: {len(new_template)} символов")
        print(f"   Изменено: {len(new_template) - len(old_template):+d} символов")
    else:
        print("❌ Не найдено старое правило для замены")
        print("   Ищем:", repr(old_rule[:100]))

