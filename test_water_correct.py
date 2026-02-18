#!/usr/bin/env python3
"""Правильный сценарий: пользователь отвечает на вопрос про тип"""
import asyncio
import sys, os
sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
import django
django.setup()

from main_agent import MainAgent

async def test():
    print("=" * 100)
    print("ТЕСТ: 'нет вод' → 'горячей' → 'в квартире'")
    print("=" * 100)
    
    agent = MainAgent()
    session = "test_water_correct_20260218"
    history = []
    
    # Шаг 1: "нет вод"
    print("\n--- ШАГ 1: 'нет вод' ---")
    r1 = await agent.process_service_detection(
        message_text="нет вод",
        user_context={'session_id': session, 'channel': 'web', 'user_id': 999, 'dialog_history': history}
    )
    print(f"Статус: {r1['status']}")
    print(f"Сообщение: {r1['message']}")
    
    history.append({'role': 'user', 'text': 'нет вод'})
    history.append({'role': 'bot', 'text': r1['message'], 'metadata': r1.get('_metadata', {})})
    
    # Шаг 2: "горячей" (ПРАВИЛЬНЫЙ ответ!)
    print("\n--- ШАГ 2: 'горячей' ---")
    r2 = await agent.process_service_detection(
        message_text="горячей",
        user_context={'session_id': session, 'channel': 'web', 'user_id': 999, 'dialog_history': history}
    )
    print(f"Статус: {r2['status']}")
    print(f"Сообщение: {r2['message']}")
    print(f"Услуга: {r2.get('service_name', 'Не определена')}")
    
    if r2['status'] == 'SUCCESS':
        print("\n✅ ПРАВИЛЬНЫЙ СЦЕНАРИЙ: бот создал заявку!")
    else:
        print("\n⚠️ Нужно уточнение")

asyncio.run(test())
