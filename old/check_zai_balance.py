#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка баланса Z.ai (GLM Coding Pro)

Использование:
    python check_zai_balance.py

Примечание: Z.ai НЕ предоставляет публичный API для проверки баланса подписки.
Баланс можно проверить только через веб-интерфейс.
"""

import os
import requests
import json
from datetime import datetime, timedelta

# API ключ из .env
ZAI_API_KEY = os.getenv('ZAI_API_KEY', 'dddb23bdb2f24b94ad56f6c80a092707.nERgYekO774pIg90')


def test_api_key():
    """Проверяет валидность API ключа через тестовый запрос к GLM-4"""

    print("=" * 80)
    print("📊 ПРОВЕРКА API КЛЮЧА Z.AI")
    print("=" * 80)

    # Z.ai GLM-4 API endpoint
    api_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

    headers = {
        "Authorization": f"Bearer {ZAI_API_KEY}",
        "Content-Type": "application/json"
    }

    # Тестовый запрос
    payload = {
        "model": "glm-4",
        "messages": [
            {"role": "user", "content": "Привет"}
        ],
        "max_tokens": 10
    }

    print("\n🔍 ПРОВЕРКА ВАЛИДНОСТИ API КЛЮЧА:")
    print("-" * 80)

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=10)

        if response.status_code == 200:
            print("✅ API ключ ВАЛИДНЫЙ")
            data = response.json()

            # Извлекаем информацию о tok
            if 'usage' in data:
                usage = data['usage']
                print(f"\n📊 Информация о запросе:")
                print(f"  Input tokens: {usage.get('prompt_tokens', 'N/A')}")
                print(f"  Output tokens: {usage.get('completion_tokens', 'N/A')}")
                print(f"  Total tokens: {usage.get('total_tokens', 'N/A')}")

            return True

        elif response.status_code == 401:
            print("❌ API ключ НЕВАЛИДНЫЙ или истек")
            print(response.text)
            return False

        elif response.status_code == 429:
            print("⚠️ API ключ валиден, но ИСЧЕРПАН лимит токенов")
            print("\n💡 Решение:")
            print("   1. Проверьте баланс через веб-интерфейс (см. ниже)")
            print("   2. Подождите восстановления 5-часового окна")
            print("   3. Или пополните баланс")
            return True

        else:
            print(f"❌ Ошибка API: {response.status_code}")
            print(response.text)
            return False

    except Exception as e:
        print(f"❌ Ошибка при проверке API ключа: {e}")
        return False


def show_web_interface_instructions():
    """Показывает инструкции как проверить баланс через веб-интерфейс"""

    print("\n" + "=" * 80)
    print("🌐 КАК ПРОВЕРИТЬ БАЛАНС ЧЕРЕЗ ВЕБ-ИНТЕРФЕЙС")
    print("=" * 80)

    print("""
📍 Z.ai НЕ предоставляет публичный API для проверки баланса подписки.
   Баланс можно проверить ТОЛЬКО через веб-интерфейс.

🔹 СПОСОБ 1: Основная консоль (для API ключей и баланса)

   1. Откройте: https://console.bigmodel.cn/
   2. Войдите в аккаунт (если не вошли)
   3. В верхнем меню выберите: 财务 (Финансы)
   4. Выберите: 我的余额 (Мой баланс)
   5. Там увидите:
      - Общий баланс токенов
      - Информацию о подписках
      - Историю расходов

🔹 СПОСОБ 2: Управление подписками GLM Coding Plan

   1. Откройте: https://console.bigmodel.cn/
   2. В верхнем меню выберите: 财务 (Финансы)
   3. Выберите: 订阅管理 (Управление подписками)
   4. Там увидите:
      - Тип подписки (Lite/Pro/Max)
      - Текущее использование промптов
      - Лимит промптов на 5 часов
      - Время до восстановления лимита
      - Дату окончания подписки

🔹 СПОСОБ 3: Основной сайт z.ai (для GLM Coding Plan)

   1. Откройте: https://z.ai/subscribe
   2. Войдите в аккаунт
   3. Раздел "My Coding Plan" покажет:
      - Ваш текущий план
      - Использование промптов
      - Статус подписки

💡 ПОЛЕЗНЫЕ ССЫЛКИ:
   - Консоль: https://console.bigmodel.cn/
   - Подписки: https://z.ai/subscribe
   - Документация: https://docs.bigmodel.cn/cn/coding-plan/overview
   - FAQ: https://docs.bigmodel.cn/cn/faq/coding-plan
""")

    print("\n⏰  КАК РАБОТАЮТ ЛИМИТЫ GLM CODING PLAN:")
    print("-" * 80)

    print("""
📦 Pro план (45 $/месяц):
  - Лимит: ~600 промптов / 5 часов
  - Скользящее окно: каждые 5 часов лимит полностью восстанавливается

⏱️  Пример:
  - 10:00 - начали использовать, 0 промптов
  - 11:30 - использовали 200 промптов, осталось 400
  - 12:00 - использовали все 600, лимит исчерпан
  - 15:00 - прошло 5 часов с первого промпта, лимит восстановлен
  - В скользящее окно попадают только промпты за последние 5 часов

💡 Если видите ошибку "rate limit" или "insufficient quota":
  1. Подождите 5 часов для полного восстановления
  2. Или проверьте баланс через веб-интерфейс
  3. Или обновите подписку до Max (2400 промптов / 5 часов)
""")

    print("=" * 80)


def show_pricing_info():
    """Показывает справочную информацию о тарифах"""

    print("\n📋 СПРАВОЧНАЯ ИНФОРМАЦИЯ О ТАРИФАХ:")
    print("-" * 80)

    print("""
📦 GLM CODING PLAN (подписка):

┌──────────┬──────────────┬─────────────────────────────────┐
│ План     │ Цена/месяц   │ Лимит                           │
├──────────┼──────────────┼─────────────────────────────────┤
│ Lite     │ 20 ¥ (~$3)   │ ~120 промптов / 5 часов         │
│          │              │ Эквивалент Claude Pro × 3       │
├──────────┼──────────────┼─────────────────────────────────┤
│ Pro      │ ~45 $        │ ~600 промптов / 5 часов         │
│          │              │ Эквивалент Claude Max(5x) × 3    │
├──────────┼──────────────┼─────────────────────────────────┤
│ Max      │ ~90 $        │ ~2400 промптов / 5 часов        │
│          │              │ Эквивалент Claude Max(20x) × 3   │
└──────────┴──────────────┴─────────────────────────────────┘

💡 Скорость генерации: 55+ tokens/сек
💡 Эквивалент API: 0.1% от цены API (в 1000 раз дешевле!)
💡 Примерный расчет: 1 промпт = 15-20 вызовов модели = ~15-20K tokens
""")

    print("=" * 80)


if __name__ == '__main__':
    # 1. Проверяем API ключ
    api_valid = test_api_key()

    # 2. Показываем инструкции для веб-интерфейса
    show_web_interface_instructions()

    # 3. Показываем информацию о тарифах
    show_pricing_info()

    print("\n✅ Готово!")
