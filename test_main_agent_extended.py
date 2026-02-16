#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Расширенное тестирование
"""

import os
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
django.setup()

from ai_agent_service import AIAgentService
from llm_tester.models import PromptTemplate

async def test():
    tmpl = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()

    catalog = '- #Сантехника #Водоснабжение #Канализация #Отопление #Батарея #Радиатор\n- #Электроснабжение #Электрика #Свет\n- #Газоснабжение #Газ #Плита\n- #Лифт #Мусоропровод #Домофон\n- #Окна #Двери #Балкон #Лоджия\n- #Кровля #Фасад #Крыша\n- #Двор #Детская #Площадка #Парковка\n- #Подвал #Подпол\n- #Кондиционер #Сплит-система\n- #Прочее'

    examples = [
        {"msg": "Прорвало трубу, вода везде", "ctx": "", "note": "Сантехника, срочно"},
        {"msg": "Батарея холодная", "ctx": "", "note": "Отопление"},
        {"msg": "Фонарь во дворе не горит", "ctx": "", "note": "Общедомовое"},
        {"msg": "Здравствуйте", "ctx": "", "note": "Приветствие"},
        {"msg": "Помогите", "ctx": "", "note": "Общий запрос"},
    ]

    ai = AIAgentService()

    for i, ex in enumerate(examples, 1):
        print(f"\n{'='*70}")
        print(f"[{i}] {ex['msg']}")
        print(f"    ({ex['note']})")
        print('='*70)

        vars = {
            'message_text': ex['msg'],
            'context': ex['ctx'],
            'SERVICE_CATALOG': catalog,
            'KNOWLEDGE_BASE': ''
        }

        prompt = tmpl.template
        for k, v in vars.items():
            prompt = prompt.replace(f'{{{{{k}}}}}', v)

        try:
            resp, usage = await ai.call_llm(
                prompt=prompt,
                provider="yandexgpt",
                temperature=0.3,
                max_tokens=300
            )

            print(f"📨 {resp}")
            print(f"💰 {usage.get('cost_rub', 0):.4f} руб | {resp.count('?')} ? | {len(resp.split())} слов")

        except Exception as e:
            print(f"❌ {e}")

asyncio.run(test())
