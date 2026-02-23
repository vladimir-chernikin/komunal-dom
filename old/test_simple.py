#!/usr/bin/env python
"""
Простой тест для проверки фильтрации
"""
import os
import sys
import asyncio

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from main_agent import MainAgent
from problem_accumulation_service import ProblemAccumulationService
from filter_detection_service import FilterDetectionService
from ai_agent_service import AIAgentService

async def main():
    print("Инициализация сервисов...")
    ai_agent = AIAgentService()
    problem_accumulator = ProblemAccumulationService(ai_agent)
    filter_detection = FilterDetectionService(ai_agent)

    agent = MainAgent()
    agent.ai_agent = ai_agent
    agent.filter_detection = filter_detection
    agent.problem_accumulator = problem_accumulator

    print("✅ Сервисы инициализированы")
    print()
    print("ТЕСТ 1: Простое сообщение 'у меня прорвало трубу'")
    print("-" * 60)

    try:
        result = await agent.process_service_detection(
            message_text='у меня прорвало трубу',
            user_context={}
        )

        print(f"✅ Тест завершен")
        print(f"Статус: {result.get('status')}")
        print(f"Сообщение: {result.get('message', '')[:100]}")
        print(f"Кандидатов: {len(result.get('candidates', []))}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
