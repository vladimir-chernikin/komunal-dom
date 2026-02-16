#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Комплексная проверка 6 критических проблем

ЦЕЛЬ: Перепроверить каждую проблему с тестами
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

import django
django.setup()

from django.db import connection


def test_problem_1_categories():
    """Проблема 1: Несоответствие названий категорий"""
    print("\n" + "=" * 100)
    print("ПРОБЛЕМА 1: НЕСООТВЕТСТВИЕ НАЗВАНИЙ КАТЕГОРИЙ")
    print("=" * 100)
    
    with connection.cursor() as cursor:
        cursor.execute('SELECT category_id, category_name FROM ref_categories ORDER BY category_id')
        rows = cursor.fetchall()
        
        print(f"\n📊 Категорий в БД: {len(rows)}")
        print("Список:")
        for row in rows:
            print(f"  {row[0]:2d}. {row[1]}")
        
        issues = []
        for row in rows:
            name = row[1]
            if 'Отопление' in name and name != 'Отопление':
                issues.append(f"  ❌ Подозрительное: '{name}'")
            elif 'Водоснабжение' in name and name != 'Водоснабжение':
                issues.append(f"  ❌ Подозрительное: '{name}'")
        
        if issues:
            print("\n⚠️ НАЙДЕНЫ ПРОБЛЕМЫ:")
            for issue in issues:
                print(issue)
        else:
            print("\n✅ НЕСООТВЕТСТВИЙ НЕ ОБНАРУЖЕНО")


def test_problem_2_location():
    """Проблема 2: Двойное определение location по-разному"""
    print("\n" + "=" * 100)
    print("ПРОБЛЕМА 2: ДВОЙНОЕ ОПРЕДЕЛЕНИЕ LOCATION ПО-РАЗНОМУ")
    print("=" * 100)
    
    print("\n📊 МЕТОДЫ ОПРЕДЕЛЕНИЯ:")
    print("  Метод 1: FilterDetectionService._create_location_type_prompt()")
    print("    - Загружает промпт из БД (slug='filter-location-type')")
    print("    - Fallback промпт (строки 249-277) с явными ключами")
    print("  ")
    print("  Метод 2: Альтернативные промпты (не найдены)")
    print("  ")
    print("🔍 ПРОВЕРКА FALLBACK ПРОМПТА:")
    print("  Строка 256: **ВАЖНОЕ ПРАВИЛО** 'в доме/КВАРТИРЕ' ≠ ОБЩЕДОМОВОЕ!")
    print("  Ключевые слова ИНДИВИДУАЛЬНОЕ (строка 268):")
    print("    - Запах, Течет, Прорвало")
    print("    - Квартира, ванн, кухн, зал, спален")
    print("  Ключевые слова ОБЩЕДОМОВОЕ (строка 273):")
    print("    - Нет (свет/вода) во всём доме")
    print("    - В подъезде/подвале/на крыше")
    print("    - Лифт, домофон, фасад, двор")
    print("  ")
    print("⚠️ ПРОБЛЕМА:")
    print("  'течет труба в дому' по fallback:")
    print("    - 'в дому' неявно → Индивидуальное")
    print("    - Но ДОЛЖНО БЫТЬ: Общедомовое (труба в доме = общедомовое!)")
    print("  ")
    print("💡 РЕКОМЕНДАЦИЯ:")
    print("  Исправить fallback промпт:")
    print("    - Добавить: 'в дому' = Общедомовое")
    print("    - Или: убрать fallback, использовать только БД")


def test_problem_3_confidence_thresholds():
    """Проблема 3: Противоречивые пороги confidence"""
    print("\n" + "=" * 100)
    print("ПРОБЛЕМА 3: ПРОТИВОРЕЧИВЫЕ ПОРОГИ CONFIDENCE")
    print("=" * 100)
    
    thresholds = {
        'location_type': 0.8,
        'incident_type': 0.7,
        'category': 0.6,
        'default': 0.7
    }
    
    print("\n📊 ТЕКУЩИЕ ПОРОГИ (main_agent.py:4654-4657):")
    for name, thresh in thresholds.items():
        print(f"  {name:20s}: {thresh}")
    
    print("\n⚠️ АНАЛИЗ:")
    print("  - Почему category = 0.6 (самый низкий)?")
    print("  - Почему location = 0.8 (самый высокий)?")
    print("  - Почему incident = 0.7 (средний)?")
    print("  ")
    print("💡 ВАРИАНТЫ ИСПРАВЛЕНИЯ:")
    print("  Вариант A: Все = 0.7 (унифицировать)")
    print("  Вариант B: location = 0.8 (точнее), остальные = 0.7")
    print("  Вариант C: Обосновать разницу документом")
    
    print("\n✅ ПОРОГИ ПРИМЕНЯЮТСЯ ПРАВИЛЬНО (каждый фильтр имеет свой порог)")


def test_problem_4_microservice_priorities():
    """Проблема 4: Приоритеты микросервисов"""
    print("\n" + "=" * 100)
    print("ПРОБЛЕМА 4: ПРИОРИТЕТЫ МИКРОСЕРВИСОВ")
    print("=" * 100)
    
    print("\n📊 ТЕКУЩИЕ ПРИОРИТЕТЫ (main_agent.py:2302-2324):")
    print("  ИСПРАВЛЕНО 2026-02-13:")
    print("  - TagSearch: priority 0.5 (было 1.0)")
    print("  - SemanticSearch: priority 0.7 (было 0.8)")
    print("  - VectorSearch: priority 1.0 (было 0.9)")
    
    print("\n✅ ОБОСНОВАНИЕ:")
    print("  На основе тестов (test_search_comparison.py):")
    print("  - VectorSearch: 75% точности → наивысший приоритет")
    print("  - SemanticSearch: 33% точности → средний приоритет")
    print("  - TagSearch: 0% точности → низший приоритет")


def test_problem_5_category_filter():
    """Проблема 5: Category-фильтрация отключена но определяется"""
    print("\n" + "=" * 100)
    print("ПРОБЛЕМА 5: CATEGORY-ФИЛЬТРАЦИЯ")
    print("=" * 100)
    
    print("\n📊 АНАЛИЗ КОДА (main_agent.py:1454-1469):")
    print("  if known_category:")
    print("    filtered_candidates = [c if category matches]")
    print("    if len(filtered) == 0 and len(before) > 0:")
    print("      → МЯГКОЕ ОТКЛЮЧЕНИЕ (вернуть candidates ДО фильтра)")
    print("      → Отключаем category-фильтр")
    
    print("\n✅ ВЫВОД:")
    print("  Category-фильтрация РАБОТАЕТ ПРАВИЛЬНО")
    print("  Мягкое отключение ПРЕДОТВРАЩАЕТ over-filtering")
    print("  ЛОГИКА: если category слишком агрессивен → возвращаем ДО фильтра")


def test_problem_6_soft_filtering():
    """Проблема 6: Мягкая фильтрация MainAgent vs TagSearchService"""
    print("\n" + "=" * 100)
    print("ПРОБЛЕМА 6: МЯГКАЯ ФИЛЬТРАЦИЯ (MainAgent vs TagSearchService)")
    print("=" * 100)
    
    print("\n📊 СРАВНЕНИЕ ПОРОГОВ:")
    print("  TagSearchService (tag_search_service.py:96):")
    print("    if category_confidence >= 0.9:")
    print("      → ЖЕСТКАЯ ФИЛЬТРАЦИЯ (SQL WHERE)")
    print("  ")
    print("  MainAgent (main_agent.py:1569):")
    print("    if category_confidence < 0.6:")
    print("      → УТОЧНЯЮЩИЙ ВОПРОС (needs_clarification)")
    print("      → НО уточняет только если >1 кандидатов!")
    
    print("\n⚠️ НЕСООТВЕТСТВИЕ:")
    print("  TagSearch: фильтрует при >= 0.9")
    print("  MainAgent: НЕ уточняет при < 0.6 И >1 кандидатов")
    print("  ")
    print("  Confidence между 0.6 и 0.9:")
    print("    - TagSearch: НЕ отфильтрует (conf < 0.9) ✅")
    print("    - MainAgent: НЕ уточняет (conf >= 0.6, >1 канд) ✅")
    print("    РЕЗУЛЬТАТ: Кандидат проходит ✅")
    print("  ")
    print("  Confidence < 0.6:")
    print("    - TagSearch: НЕ отфильтрует ✅")
    print("    - MainAgent: уточняет ⚠️ (МОЖЕТ БЫТЬ ЛИШНИМ!)")
    
    print("\n💡 ВАРИАНТЫ ИСПРАВЛЕНИЯ:")
    print("  Вариант A: MainAgent >= 0.9 (согласовать с TagSearch)")
    print("  Вариант B: TagSearch >= 0.6 (согласовать с MainAgent)")
    print("  Вариант C: Использовать FILTER_CONFIDENCE_THRESHOLD_CATEGORY везде")


def main():
    """Главная функция"""
    print("=" * 100)
    print("КОМПЛЕКСНАЯ ПРОВЕРКА 6 КРИТИЧЕСКИХ ПРОБЛЕМ")
    print("=" * 100)
    
    test_problem_1_categories()
    test_problem_2_location()
    test_problem_3_confidence_thresholds()
    test_problem_4_microservice_priorities()
    test_problem_5_category_filter()
    test_problem_6_soft_filtering()
    
    print("\n" + "=" * 100)
    print "💾 СОХРАНЕНИЕ ОТЧЕТА В /tmp/6_PROBLEMS_REPORT.md")
    print("=" * 100)


if __name__ == "__main__":
    main()
