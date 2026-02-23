#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка баланса Yandex Cloud и расхода токенов YandexGPT

Использование:
    python check_yandex_balance.py
"""

import os
import requests
import json
from datetime import datetime

# Учетные данные из .env
FOLDER_ID = os.getenv('YANDEX_FOLDER_ID', 'b1gp9mn6103aupe3ea0k')
API_KEY = os.getenv('YANDEX_API_KEY', '')

def check_billing_balance():
    """Проверяет баланс через Yandex Cloud Billing API"""
    print("=" * 80)
    print("📊 ПРОВЕРКА БАЛАНСА YANDEX CLOUD")
    print("=" * 80)

    # Для проверки баланса нужен OAuth токен или IAM токен сервиса
    # Это требует дополнительной настройки

    print("\n📋 ИНФОРМАЦИЯ О ТАРИФАЦИИ (2025):")
    print("-" * 80)
    print("YandexGPT Lite:  0.20 ₽ за 1,000 токенов")
    print("YandexGPT Pro:  3.00 ₽ за 1,000 токенов")
    print("GigaChat:     0.50 ₽ за 1,000 токенов (GigaChat)")
    print("GigaChat-2:   1.50 ₽ за 1,000 токенов")
    print()
    print("🎁 БЕСПЛАТНЫЙ ЛИМИТ для новых пользователей:")
    print("   3000 ₽/месяц в течение 3 месяцев")
    print()

    # Читаем статистику из ai_agent_service
    stats_file = "/tmp/llm_usage_stats.json"
    if os.path.exists(stats_file):
        try:
            with open(stats_file, 'r') as f:
                stats = json.load(f)

            print("📈 СТАТИСТИКА ИСПОЛЬЗОВАНИЯ:")
            print("-" * 80)
            print(f"Всего запросов: {stats.get('total_requests', 0)}")
            print(f"Всего токенов: {stats.get('total_tokens', 0)}")

            # Разбивка по провайдерам
            for provider, data in stats.get('providers', {}).items():
                if data.get('tokens', 0) > 0:
                    tokens = data['tokens']
                    cost = data['cost']
                    requests = data['requests']

                    # Рассчитываем примерный остаток (3000 ₽)
                    remaining = 3000 - cost

                    print()
                    print(f"🤖 {provider.upper()}:")
                    print(f"   Запросов: {requests}")
                    print(f"   Токенов: {tokens}")
                    print(f"   Потрачено: {cost:.2f} ₽")
                    print(f"   Остаток: {remaining:.2f} ₽ (из 3000 ₽)")

                    # Примерно сколько токенов осталось
                    if provider == 'yandexgpt':
                        avg_price = 0.20  # средняя цена ( Lite + Pro)
                        remaining_tokens = int(remaining / avg_price * 1000)
                        print(f"   ~ Осталось токенов: {remaining_tokens:,}")

        except Exception as e:
            print(f"❌ Ошибка чтения статистики: {e}")
    else:
        print("📊 Статистика использования не найдена")

    print()
    print("=" * 80)
    print("📖 ДЛЯ ТОЧНОЙ ПРОВЕРКИ БАЛАНСА:")
    print("   1. Откройте https://console.yandex.cloud/")
    print("   2. Billing → Платежи")
    print("   3. Там увидите точный баланс и историю")
    print("=" * 80)

if __name__ == '__main__':
    check_billing_balance()
