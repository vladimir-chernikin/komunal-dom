#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Быстрый тест RAG-промпта MainAgent

Дата: 2026-02-18
Цель: Проверить что RAG-промпт загружается и работает
"""

import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from llm_tester.models import PromptTemplate

def test_rag_prompt():
    """Проверка RAG-промпта в БД"""
    print("=== ТЕСТ RAG-ПРОМПТА ===\n")

    # Загружаем промпт
    prompt = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()

    if not prompt:
        print("❌ Промпт не найден!")
        return False

    print(f"✅ Промпт найден:")
    print(f"   ID: {prompt.id}")
    print(f"   Slug: {prompt.slug}")
    print(f"   Name: {prompt.name}")
    print(f"   Length: {len(prompt.template)} символов\n")

    # Проверяем ключевые секции
    template = prompt.template

    checks = [
        ("RAG-архитектура", "RAG" in template or "БАЗА ЗНАНИЙ" in template),
        ("Safety-check", "Safety-check" in template or "газ/пожар" in template),
        ("NEGATIVE mode", "NEGATIVE" in template),
        ("MODE (CHAT/TRIAGE/etc)", "MODE:" in template or "CHAT:" in template),
        ("Воронка (7 этапов)", "воронк" in template.lower() or "7 этап" in template),
        ("5-шаговый алгоритм", "5-шаг" in template or "алгоритм" in template),
        ("txtPrb (память диалога)", "txtPrb" in template),
        ("OBJ/EVENT/PLACE (сущности)", "OBJ" in template and "EVENT" in template and "PLACE" in template),
        ("RAG: KNOWLEDGE_BASE", "KNOWLEDGE_BASE" in template),
        ("RAG: SERVICE_CATALOG", "SERVICE_CATALOG" in template),
        ("Правила: ≤10 слов", "10 слов" in template),
        ("Правила: без эмодзи", "эмодзи" in template or "emoji" in template.lower()),
    ]

    print("📊 Проверка функционала:")
    for name, result in checks:
        status = "✅" if result else "❌"
        print(f"   {status} {name}")

    all_passed = all(result for _, result in checks)

    print(f"\n{'='*60}")
    if all_passed:
        print("✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ! RAG-ПРОМПТ ПОЛНОЦЕННЫЙ!")
    else:
        print("⚠️  Некоторые проверки не пройдены")
    print(f"{'='*60}\n")

    # Показываем первые 500 символов
    print("📄 ПЕРВЫЕ 500 СИМВОЛОВ ПРОМПТА:")
    print(f"{'='*60}")
    print(template[:500])
    print(f"{'='*60}\n")

    return all_passed

if __name__ == '__main__':
    success = test_rag_prompt()
    sys.exit(0 if success else 1)
