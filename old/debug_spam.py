#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Отладка anti-spam фильтра
"""

import os
import sys

# Django setup
sys.path.append('/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from service_detection_modules import AntiSpamFilter

def debug_spam_filter():
    """Отлаживаем anti-spam фильтр"""

    print("🔍 Отладка anti-spam фильтра...")

    try:
        spam_filter = AntiSpamFilter()

        test_messages = [
            "Протекает кран на кухне",
            "Забилась раковина в ванной",
            "Нет света в квартире",
            "Перегорела лампочка",
            "Из потолка капает вода"
        ]

        for message in test_messages:
            print(f"\n📝 Тестовое сообщение: '{message}'")

            # Проверяем spam keywords
            text_lower = message.lower()
            print(f"🔤 В нижнем регистре: '{text_lower}'")

            spam_detected = False
            for keyword in spam_filter.SPAM_KEYWORDS:
                if keyword in text_lower:
                    print(f"❌ Найден spam keyword: '{keyword}'")
                    spam_detected = True
                    break

            if not spam_detected:
                print("✅ Spam keywords не найдены")

            # Проверяем длину
            words = message.split()
            print(f"📊 Количество слов: {len(words)}, минимум: {spam_filter.MIN_MESSAGE_LENGTH}")

            # Проверяем результат
            result = spam_filter.check_message(message)
            print(f"🎯 Результат: {result}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    debug_spam_filter()