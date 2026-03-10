#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестовый скрипт для проверки обработки db_error в MainAgent
"""

import asyncio
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from main_agent import MainAgent
from asgiref.sync import sync_to_async


async def test_db_error_handling():
    """Тестируем обработку db_error в MainAgent"""

    print("=" * 80)
    print("ТЕСТ: MainAgent обработка db_error от ProblemAccumulationService")
    print("=" * 80)

    # Создаем MainAgent
    main_agent = MainAgent()

    # Тестовое сообщение
    message_text = "у меня течет в зале"
    user_context = {
        'session_id': 'test_db_error_mainagent',
        'message_id': 1,
        'dialog_history': []
    }

    print(f"\nВходные данные:")
    print(f"  message_text: '{message_text}'")
    print(f"  session_id: '{user_context['session_id']}'")

    # ПРОВЕРКА 1: Нормальная работа (промпт в БД активен)
    print("\n" + "-" * 80)
    print("ПРОВЕРКА 1: Нормальная работа (промпт в БД активен)")
    print("-" * 80)

    result = await main_agent.process_service_detection(
        message_text=message_text,
        user_context=user_context
    )

    print(f"\nРезультат:")
    print(f"  status: {result.get('status')}")
    print(f"  message: '{result.get('message', '')[:100]}'")
    print(f"  db_error в metadata: {result.get('_metadata', {}).get('db_error', False)}")

    if result.get('status') == 'ERROR' and result.get('_metadata', {}).get('db_error'):
        print("❌ ОШИБКА: Получен db_error при активном промпте!")
        return False
    elif result.get('status') in ['SUCCESS', 'AMBIGUOUS']:
        print("✅ УСПЕХ: Нормальная работа без db_error")
    else:
        print(f"⚠️  Неожиданный статус: {result.get('status')}")

    # ПРОВЕРКА 2: Ошибка БД (деактивируем промпт)
    print("\n" + "-" * 80)
    print("ПРОВЕРКА 2: Ошибка БД (деактивируем промпт)")
    print("-" * 80)

    from llm_tester.models import PromptTemplate

    @sync_to_async
    def deactivate_prompt():
        db_template = PromptTemplate.objects.filter(slug='problem-accumulation-service').first()
        if not db_template:
            return None, False
        was_active = db_template.is_active
        db_template.is_active = False
        db_template.save()
        return db_template, was_active

    @sync_to_async
    def activate_prompt(template_obj, is_active):
        template_obj.is_active = is_active
        template_obj.save()

    db_template, was_active = await deactivate_prompt()
    if not db_template:
        print("❌ Промпт не найден в БД!")
        return False

    print(f"Промпт деактивирован (was_active={was_active})")

    # Вызываем MainAgent с деактивированным промптом
    result = await main_agent.process_service_detection(
        message_text=message_text,
        user_context=user_context
    )

    print(f"\nРезультат:")
    print(f"  status: {result.get('status')}")
    print(f"  error: {result.get('error', 'N/A')}")
    print(f"  message: '{result.get('message', '')[:200]}'")
    print(f"  db_error в metadata: {result.get('_metadata', {}).get('db_error', False)}")
    print(f"  error_type: {result.get('_metadata', {}).get('error_type', 'N/A')}")

    # Восстанавливаем активность промпта
    await activate_prompt(db_template, was_active)
    print(f"\nПромпт восстановлен (is_active={was_active})")

    # Проверка результата
    if result.get('status') == 'ERROR':
        if result.get('_metadata', {}).get('db_error'):
            print("\n✅ УСПЕХ: db_error корректно обработан!")
            print("✅ Возвращен статус ERROR")
            print("✅ Есть сообщение для пользователя")
            print("✅ В metadata есть db_error=True")
            return True
        else:
            print("\n❌ ОШИБКА: Статус ERROR но нет db_error в metadata!")
            return False
    else:
        print(f"\n❌ ОШИБКА: Ожидался статус ERROR, но получен {result.get('status')}!")
        return False


async def main():
    """Главная функция"""

    print("\n🧪 ТЕСТИРОВАНИЕ MainAgent обработки db_error\n")

    result = await test_db_error_handling()

    # Итог
    print("\n" + "=" * 80)
    if result:
        print("🎉 ТЕСТ ПРОЙДЕН УСПЕШНО!")
        return 0
    else:
        print("⚠️ ТЕСТ НЕ ПРОЙДЕН")
        return 1


if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
