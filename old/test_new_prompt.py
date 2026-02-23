#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестовый скрипт для проверки нового промпта mainagent-orchestrator

Запуск: python test_new_prompt.py
"""

import os
import sys
import django

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
sys.path.insert(0, '/var/www/komunal-dom_ru')
django.setup()

from llm_tester.models import PromptTemplate


def test_prompt_template():
    """Проверяет загрузку промпта из БД"""

    print("=" * 70)
    print("ТЕСТ: Загрузка промпта mainagent-orchestrator из БД")
    print("=" * 70)

    # Загружаем промпт
    db_template = PromptTemplate.objects.filter(
        slug='mainagent-orchestrator',
        is_active=True
    ).first()

    if not db_template:
        print("❌ ОШИБКА: Промпт не найден в БД!")
        return False

    print(f"\n✅ Промпт найден:")
    print(f"   ID: {db_template.id}")
    print(f"   Название: {db_template.name}")
    print(f"   Slug: {db_template.slug}")
    print(f"   Длина: {len(db_template.template)} символов")
    print(f"   Обновлен: {db_template.updated_at}")

    # Проверяем наличие переменных
    template = db_template.template
    required_vars = [
        '{{absolute_facts}}',
        '{{txtPrb}}',
        '{{dialog_history}}',
        '{{established_filters}}',
        '{{candidates}}'
    ]

    print(f"\n📋 Проверка переменных в шаблоне:")
    for var in required_vars:
        if var in template:
            print(f"   ✅ {var} - найдена")
        else:
            print(f"   ❌ {var} - НЕ НАЙДЕНА!")

    # Тест подстановки переменных
    print(f"\n🔄 Тест подстановки переменных:")
    test_vars = {
        'absolute_facts': '- УЖЕ ИЗВЕСТНЫЙ объект: батарея\n- УЖЕ ИЗВЕСТНА локация: зал',
        'txtPrb': 'У пользователя течёт батарея в зале',
        'dialog_history': 'Пользователь: Привет\nБот: Здравствуйте! Что случилось?',
        'established_filters': "{'object_description': {'value': 'течь', 'confidence': 0.9}}",
        'candidates': '1. Прорыв батареи (Отопление, Индивидуальное)'
    }

    try:
        formatted_prompt = template.format(**test_vars)
        print(f"   ✅ Подстановка прошла успешно!")
        print(f"\n📝 Результат (первые 500 символов):")
        print("-" * 70)
        print(formatted_prompt[:500])
        print("-" * 70)

        return True
    except Exception as e:
        print(f"   ❌ Ошибка подстановки: {e}")
        return False


if __name__ == '__main__':
    success = test_prompt_template()
    print(f"\n{'=' * 70}")
    if success:
        print("✅ ТЕСТ ПРОЙДЕН УСПЕШНО!")
    else:
        print("❌ ТЕСТ НЕ ПРОЙДЕН!")
    print("=" * 70)
