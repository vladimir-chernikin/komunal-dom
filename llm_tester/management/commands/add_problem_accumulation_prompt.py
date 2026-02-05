#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Management команда для добавления промпта ProblemAccumulationService в БД
"""

from django.core.management.base import BaseCommand
from llm_tester.models import PromptTemplate


class Command(BaseCommand):
    help = 'Добавляет промпт ProblemAccumulationService в БД'

    def handle(self, *args, **options):
        # Промпт ProblemAccumulationService
        template_content = """Ты - аналитик, извлекающий и накапливающий факты из диалога.

ТЕКУЩЕЕ ОПИСАНИЕ ПРОБЛЕМЫ:
{current_problem}

ПРЕДЫДУЩИЙ ВОПРОС БОТА (на который пользователь отвечает):
{bot_question}

ТЕКУЩЕЕ СООБЩЕНИЕ ПОЛЬЗОВАТЕЛЯ:
{message_text}
{history_context}

ЗАДАЧА:
1. Определи содержит ли сообщение ПОЛЕЗНУЮ информацию о проблеме
2. Извлеки конкретные факты из сообщения
3. Обнови описание проблемы, добавив новую информацию

ВАЖНО:
- Если "привет", "да", "нет", "ок", "спасибо", "пожалуйста" → is_meaningful=false
- ⛔ КРИТИЧЕСКИ ВАЖНО: Если bot_question содержит вопрос ("Где", "Что", "Какой"), то ответ ВСЕГДА is_meaningful=true!
  Даже если ответ короткий ("в зале", "труба", "батарея") - это ЗНАЧИМЫЙ ответ на вопрос бота!
- Объединяй информацию с current_problem (НЕ копируй, а ДОБАВЛЯЙ)
- НЕ повторяй уже известную информацию
- Извлекай МАКСИМУМ конкретики: локация, источник, категория, серьезность
- txtPrb должно быть КРАТКИМ и ПОНЯТНЫМ (1-2 предложения)
- ⛔ КРИТИЧЕСКИ ВАЖНО: Если is_meaningful=false, ТОЧНО скопируй current_problem в updated_problem БЕЗ ИЗМЕНЕНИЙ!

Верни ТОЛЬКО JSON (без markdown):

{{
    "is_meaningful": true или false,
    "new_info": "краткое описание НОВОЙ информации (5-10 слов)",
    "updated_problem": "полное обновленное описание проблемы (1-2 предложения)",
    "fields": {{
        "problem": "проблема (течет, сломался, запах, шум и т.д.)",
        "location": "локация (зал, ванная, кухня, подъезд и т.д.)",
        "source": "источник (труба, батарея, кран, розетка и т.д.)",
        "category": "категория (отопление, водоснабжение, электрика и т.д.)",
        "severity": "серьезность (авария, небольшая проблема)",
        "intensity": "интенсивность (сильно, слабо, постоянно)",
        "object": "объект (если упоминается конкретный объект)"
    }}
}}

ПРИМЕРЫ:

ПРИМЕР 1:
current_problem: "(пусто)"
bot_question: "(не было)"
message_text: "у меня течет"
Ответ:
{{
    "is_meaningful": true,
    "new_info": "у пользователя течет",
    "updated_problem": "у пользователя течет",
    "fields": {{
        "problem": "течет",
        "location": null,
        "source": null,
        "category": null,
        "severity": null,
        "intensity": null,
        "object": null
    }}
}}

ПРИМЕР 1.5 (ОТВЕТ НА ВОПРОС БОТА - ВСЕГДА ЗНАЧИМЫЙ!):
current_problem: "у пользователя прорвало трубу"
bot_question: "Где именно?"
message_text: "в квартире"
Ответ:
{{
    "is_meaningful": true,
    "new_info": "локация: квартира",
    "updated_problem": "у пользователя прорвало трубу в квартире",
    "fields": {{
        "problem": "прорвало",
        "location": "квартира",
        "source": "труба",
        "category": null,
        "severity": null,
        "intensity": null,
        "object": "труба"
    }}
}}

ПРИМЕР 1.6 (КРИТИЧЕСКИ ВАЖНО - ОБЪЕДИНЯЙ, А НЕ ЗАМЕНЯЙ!):
current_problem: "у пользователя прорыв трубы в квартире"
bot_question: "Что именно сломалось?"
message_text: "кран"
❌ НЕПРАВИЛЬНЫЙ ОТВЕТ:
{{
    "updated_problem": "кран"  ❌❌❌ ЭТО НЕВЕРНО! Ты ЗАМЕНИЛ всю проблему!
}}
✅ ПРАВИЛЬНЫЙ ОТВЕТ:
{{
    "is_meaningful": true,
    "new_info": "объект: кран",
    "updated_problem": "у пользователя прорыв трубы в квартире, сломался кран",
    "fields": {{
        "problem": "прорыв",
        "location": "квартира",
        "source": "труба",
        "category": null,
        "object": "кран"
    }}
}}

ПРИМЕР 2:
current_problem: "у пользователя течет"
bot_question: "Где именно?"
message_text: "В зале"
Ответ:
{{
    "is_meaningful": true,
    "new_info": "локация: зал",
    "updated_problem": "у пользователя течет в зале",
    "fields": {{
        "problem": "течет",
        "location": "зал",
        "source": null,
        "category": null,
        "severity": null,
        "intensity": null,
        "object": null
    }}
}}

ПРИМЕР 3:
current_problem: "у пользователя течет в зале"
bot_question: "Что именно течет?"
message_text: "Батарея"
Ответ:
{{
    "is_meaningful": true,
    "new_info": "источник: батарея (отопление)",
    "updated_problem": "у пользователя течет из батареи (отопление) в зале",
    "fields": {{
        "problem": "течет",
        "location": "зал",
        "source": "батарея",
        "category": "отопление",
        "severity": null,
        "intensity": null,
        "object": "батарея"
    }}
}}

ПРИМЕР 4 (НЕЗНАЧИМЫЕ СООБЩЕНИЯ):
current_problem: "у пользователя течет из батареи в зале"
bot_question: "Какой напор?"
message_text: "постоянно"
Ответ:
{{
    "is_meaningful": false,
    "new_info": "интенсивность: постоянно",
    "updated_problem": "у пользователя течет из батареи в зале постоянно",
    "fields": {{
        "problem": "течет",
        "location": "зал",
        "source": "батарея",
        "category": "отопление",
        "severity": null,
        "intensity": "постоянно",
        "object": "батарея"
    }}
}}

ПРИМЕР 5 (НЕЗНАЧИМЫЕ СООБЩЕНИЯ):
current_problem: "у пользователя течет"
bot_question: null
message_text: "Привет!"
Ответ:
{{
    "is_meaningful": false,
    "new_info": "",
    "updated_problem": "у пользователя течет",
    "fields": {{
        "problem": "течет",
        "location": null,
        "source": null,
        "category": null,
        "severity": null,
        "intensity": null,
        "object": null
    }}
}}

ПРИМЕР 6 (НЕЗНАЧИМЫЕ СООБЩЕНИЯ - сохранение контекста):
current_problem: "у пользователя течет из трубы у батареи в зале"
bot_question: "Какой характер у течи?"
message_text: "а зачем тебе это?"
Ответ:
{{
    "is_meaningful": false,
    "new_info": "",
    "updated_problem": "у пользователя течет из трубы у батареи в зале",
    "fields": {{
        "problem": "течет",
        "location": "зал",
        "source": "труба у батареи",
        "category": null,
        "severity": null,
        "intensity": null,
        "object": "труба"
    }}
}}

ВАЖНО ПРИМЕЧАНИЕ: В примере 6 updated_problem ТОЧНО совпадает с current_problem!

JSON:"""

        # Создаем или обновляем шаблон
        prompt_template, created = PromptTemplate.objects.update_or_create(
            slug='problem-accumulation-service',
            defaults={
                'name': 'ProblemAccumulationService',
                'prompt_type': 'problem_accumulation',
                'template': template_content,
                'description': 'Микросервис для итеративного накопления описания проблемы из диалога. Извлекает и накапливает факты (проблема, локация, источник, категория) из коротких сообщений пользователя.',
                'is_active': True,
            }
        )

        if created:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Промпт ProblemAccumulationService успешно создан (ID: {prompt_template.id})')
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f'✅ Промпт ProblemAccumulationService успешно обновлен (ID: {prompt_template.id})')
            )

        # Показываем переменные в шаблоне
        variables = prompt_template.get_variables()
        self.stdout.write(f'📝 Переменные в шаблоне: {", ".join(variables) if variables else "Нет"}')
