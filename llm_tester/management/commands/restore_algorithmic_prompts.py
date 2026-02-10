#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Management команда для восстановления полных алгоритмических промптов FilterDetectionService

ИСПОЛЬЗОВАНИЕ:
    python manage.py restore_algorithmic_prompts

ВОССТАНАВЛИВАЕТ:
- filter-incident-type (ID: 3)
- filter-location-type (ID: 4)

ДАТА СОЗДАНИЯ: 2026-02-10
ПРИЧИНА: Восстановление промптов после случайного удаления
"""

from django.core.management.base import BaseCommand
from llm_tester.models import PromptTemplate


class Command(BaseCommand):
    help = 'Восстанавливает полные алгоритмические промпты FilterDetectionService'

    def handle(self, *args, **options):
        # Полный промпт для incident_type
        incident_type_template = """## Роль
Ты — строгий алгоритмический классификатор типа обращения. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.

## Входные данные
TXT_PRB = "{txt_prb}"

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

        # Полный промпт для location_type
        location_type_template = """## Роль
Ты — строгий алгоритмический классификатор локации. Выполняй ТОЛЬКО алгоритм. Выход ТОЛЬКО JSON.

## Входные данные
TXT_PRB = "{txt_prb}"

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

        self.stdout.write(self.style.WARNING('=== ВОССТАНОВЛЕНИЕ АЛГОРИТМИЧЕСКИХ ПРОМПТОВ ===\n'))

        updates = [
            {
                'slug': 'filter-incident-type',
                'template': incident_type_template,
                'name': 'FilterDetection: incident_type'
            },
            {
                'slug': 'filter-location-type',
                'template': location_type_template,
                'name': 'FilterDetection: location_type'
            }
        ]

        for update in updates:
            tmpl = PromptTemplate.objects.filter(slug=update['slug']).first()
            if tmpl:
                old_len = len(tmpl.template) if tmpl.template else 0
                tmpl.template = update['template']
                tmpl.save()
                new_len = len(tmpl.template)
                self.stdout.write(
                    self.style.SUCCESS(f"✓ {update['name']} (ID: {tmpl.id})")
                )
                self.stdout.write(f"  Было: {old_len} символов")
                self.stdout.write(f"  Стало: {new_len} символов\n")
            else:
                self.stdout.write(
                    self.style.ERROR(f"✗ {update['slug']} - НЕ НАЙДЕН\n")
                )

        self.stdout.write(self.style.SUCCESS('ГОТОВО! Промпты восстановлены.'))
