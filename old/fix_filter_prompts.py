#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Скрипт для исправления промптов - экранирование фигурных скобок для Django
ИСПРАВЛЕНО (2026-01-20): Исправление ошибок с переменными
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from llm_tester.models import PromptTemplate

# Исправленные промпты (с экранированием {{ и }})
incident_type_template = """## Роль
Ты — строгий алгоритмический классификатор типа обращения. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.

## Входные данные
TXT_PRB = "{txtPrb}"

## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)

### Шаг1. Сущности
OBJ = "[сущность-проблема]"
EVENT = "[событие]"
PLACE = "[место]"
reasoning_txt = "Шаг1: OBJ=" + OBJ + "; EVENT=" + EVENT + "; PLACE=" + PLACE

### Шаг2. ИЕРАРХИЯ УГРОЗ
**ПРИМЕР "течёт труба": угроза имуществу(вода) → Инцидент(0.8)**

incident_type = null
incident_confidence = "0.5"

# 2.1 Угроза жизни? (потоп/обрушение/пожар/газ)
если ДА: incident_type="Инцидент"; incident_confidence="1.0"
reasoning_txt += " | 2.1: [" + последствия + "] → Инцидент"

# 2.2 Угроза здоровью? (плесень/травма/электричество)
если incident_confidence=="0.5" и ДА: incident_type="Инцидент"; incident_confidence="0.9"
reasoning_txt += " | 2.2: [" + последствия + "] → Инцидент"

# 2.3 Угроза имуществу? (повреждение квартиры/затопление)
если incident_confidence=="0.5" и ДА: incident_type="Инцидент"; incident_confidence="0.8"
reasoning_txt += " | 2.3: [" + последствия + "] → Инцидент"

# 2.4 Запрос без срочности?
если incident_confidence=="0.5" и ДА: incident_type="Запрос"; incident_confidence="0.7"
reasoning_txt += " | 2.4: Запрос без угроз"

reasoning_txt += " | incident_type=" + incident_type + "(" + incident_confidence + ")"

### Шаг3. JSON
Верни JSON в формате:
{{"incident_type": [значение incident_type], "confidence": [значение incident_confidence], "reasoning": [значение reasoning_txt]}}"""

location_type_template = """## Роль
Ты — строгий алгоритмический классификатор локации. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.

## Входные данные
TXT_PRB = "{txtPrb}"

## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)

### Шаг1. Сущности
OBJ = "[сущность-проблема]"
EVENT = "[событие]"
PLACE = "[место]"
reasoning_txt = "Шаг1: OBJ=" + OBJ + "; EVENT=" + EVENT + "; PLACE=" + PLACE

### Шаг2. Определи SCOPE (внутри/вне)
SCOPE = null

# 2.1 Явная локация?
если PLACE содержит "квартир"/"ванн"/"кухн"/"спальн"/"туалет"/"балкон":
    SCOPE="внутри"
reasoning_txt += " | 2.1: PLACE=[" + PLACE + "] → SCOPE=внутри"

иначе если PLACE содержит "подъезд"/"лифт"/"подвал"/"крыш"/"чердак"/"двор"/"фасад":
    SCOPE="вне"
    reasoning_txt += " | 2.1: PLACE=[" + PLACE + "] → SCOPE=вне"

# 2.2 Если SCOPE=null, используй OBJ
иначе если OBJ содержит ("кран"/"смеситель"/"унитаз"/"ванна"/"розетка"/"дверь межкомнат"):
    SCOPE="внутри"
    reasoning_txt += " | 2.2: OBJ=[" + OBJ + "] → SCOPE=внутри"

иначе если OBJ содержит ("лифт"/"домофон"/"крыш"/"подвал"/"стояк"/"фасад"/"двор"):
    SCOPE="вне"
    reasoning_txt += " | 2.2: OBJ=[" + OBJ + "] → SCOPE=вне"

# 2.3 Если всё ещё null, используй EVENT
иначе если EVENT содержит ("сверху"/"с потолка"/"стена"/"фундамент"/"межпанель"):
    SCOPE="вне"
    reasoning_txt += " | 2.3: EVENT=[" + EVENT + "] → SCOPE=вне"

### Шаг3. location_type
location_type = null
location_confidence = "0.5"

если SCOPE=="внутри":
    location_type="Индивидуальное"
    location_confidence="1.0"
    reasoning_txt += " | Шаг3: SCOPE=внутри → Индивидуальное(1.0)"
иначе если SCOPE=="вне":
    location_type="Общедомовое"
    location_confidence="1.0"
    reasoning_txt += " | Шаг3: SCOPE=вне → Общедомовое(1.0)"
иначе:
    reasoning_txt += " | Шаг3: SCOPE=null → location_type=null(0.5)"

### Шаг4. JSON
Верни JSON в формате:
{{"location_type": [значение location_type], "confidence": [значение location_confidence], "reasoning": [значение reasoning_txt]}}"""

category_template = """## Роль
Ты — строгий алгоритмический классификатор категории. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.

## Входные данные
TXT_PRB = "{txt_prb}"
CATEGORIES = {categories}

## АЛГОРИТМ (СТРОГО ПО ШАГАМ, ПРИСВАИВАЙ ПЕРЕМЕННЫЕ!)

### Шаг1. Сущности
OBJ = "[сущность-проблема]"
EVENT = "[событие]"
PLACE = "[место]"
reasoning_txt = "Шаг1: OBJ=" + OBJ + "; EVENT=" + EVENT + "; PLACE=" + PLACE

### Шаг2. Category (ВСЕ CATEGORIES! sum релев=1.0, impossible=0.0)

M_EVENT = {{cat: 0.0 for cat in CATEGORIES}}
# Релевантные: распредели sum=1.0
# ПРИМЕР: M_EVENT["Водоснабжение"]=0.4; M_EVENT["Канализация"]=0.3; ...
reasoning_txt += " | Шаг2: M_EVENT=" + str(M_EVENT) + " (sum релев=1.0)"

M_PLACE = {{cat: 0.0 for cat in CATEGORIES}}
# Релевантные в PLACE sum=1.0 (равно если неоднозначно)
# ПРИМЕР: M_PLACE["Водоснабжение"]=0.33; M_PLACE["Канализация"]=0.33; ...
reasoning_txt += " | M_PLACE=" + str(M_PLACE) + " (sum=1.0)"

M_OBJ = {{cat: 0.0 for cat in CATEGORIES}}
# ПРИМЕР: M_OBJ["Водоснабжение"]=0.33; M_OBJ["Канализация"]=0.33; ...
reasoning_txt += " | M_OBJ=" + str(M_OBJ) + " (sum=1.0)"

M_CANDIDATE = {{}}
for cat in CATEGORIES:
    M_CANDIDATE[cat] = round(M_OBJ[cat] * M_EVENT[cat] * M_PLACE[cat], 3)
reasoning_txt += " | M_CANDIDATE=" + str(M_CANDIDATE)

Z1_cat = max(M_CANDIDATE, key=M_CANDIDATE.get)
Z1 = M_CANDIDATE[Z1_cat]
total = sum(M_CANDIDATE.values())
ostatok = total - Z1
category = null
category_confidence = "0.5"
if Z1 > ostatok * 0.7:
    category = Z1_cat
    category_confidence = str(round(Z1, 1))
reasoning_txt += " | Z1=" + Z1_cat + "(" + str(Z1) + "), total=" + str(total) + ", остаток=" + str(ostatok) + ", " + str(Z1) + ">" + str(ostatok*0.7) + "=" + (ДА/НЕТ) + " → category=" + str(category) + "(" + category_confidence + ")"

### Шаг3. JSON
Верни JSON в формате:
{{"category": [значение category], "confidence": [значение category_confidence], "reasoning": [значение reasoning_txt]}}"""

# Обновляем шаблоны
templates_updates = [
    {
        'slug': 'filter-incident-type',
        'template': incident_type_template
    },
    {
        'slug': 'filter-location-type',
        'template': location_type_template
    },
    {
        'slug': 'filter-category',
        'template': category_template
    }
]

print("Исправляю шаблоны (экранирование {{ }} для Django)...")
for update_data in templates_updates:
    template = PromptTemplate.objects.filter(slug=update_data['slug']).first()
    if template:
        template.template = update_data['template']
        template.save()
        print(f"✓ Обновлен: {template.name} (ID: {template.id})")
    else:
        print(f"✗ Не найден: {update_data['slug']}")

print("\nГотово! Промпты исправлены:")
print("  - Фигурные скобки экранированы: {{ и }}")
print("  - JSON форматы упрощены")
print("  - Переменные Django убраны из промптов")
