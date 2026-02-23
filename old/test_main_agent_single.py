#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Быстрый тест одного примера
"""

import os
import django
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
django.setup()

from ai_agent_service import AIAgentService
from llm_tester.models import PromptTemplate

async def test_one():
    # Загружаем промт
    tmpl = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()

    # Формируем переменные
    message_text = "У меня течет труба в ванной"
    context = "Пользователь: Привет\nАссистент: Здравствуйте! Чем могу помочь?"

    variables = {
        'message_text': message_text,
        'context': context,
        'txtPrb': '{}',
        'established_filters_json': '{}',
        'KNOWLEDGE_BASE': '',
        'SERVICE_CATALOG': '- #Сантехника #Водоснабжение #Канализация #Отопление'
    }

    # Форматируем
    prompt = tmpl.template
    for key, value in variables.items():
        placeholder = f'{{{{{key}}}}}'
        prompt = prompt.replace(placeholder, str(value))

    print("="*80)
    print("ТЕСТ: Течет труба в ванной")
    print("="*80)
    print("\n📄 ПРОМТ (первые 1500 символов):")
    print("-"*80)
    print(prompt[:1500])
    print("...")
    print("-"*80)

    # Вызываем AI
    print("\n🤖 ВЫЗОВ AI...")
    ai_service = AIAgentService()
    response, usage = await ai_service.call_llm(
        prompt=prompt,
        provider="yandexgpt",
        temperature=0.3,
        max_tokens=500
    )

    print("\n✅ ОТВЕТ AI:")
    print("-"*80)
    print(response)
    print("-"*80)

    print(f"\n💰 СТОИМОСТЬ: {usage.get('cost_rub', 0):.4f} руб.")
    print(f"   Токенов: {usage.get('total_tokens', 0)}")

asyncio.run(test_one())
