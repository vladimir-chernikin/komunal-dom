#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Генерация embedding для услуг из services_catalog
Использует Yandex Embeddings API + NLTK stopwords + pymorphy2
"""

import asyncio
import sys
import os
sys.path.append('/var/www/komunal-dom_ru')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
import django
django.setup()

from ai_agent_service import AIAgentService
import pymorphy2
import nltk
from nltk.corpus import stopwords
from django.db import connection


# Русские stopwords из NLTK
RUSSIAN_STOPWORDS = set(stopwords.words('russian'))

# КРИТИЧЕСКИ ВАЖНО (2026-02-18): Исключаем слово "нет" из stopwords!
# ПРИЧИНА: Услуги "Нет горячей воды", "Нет света" и т.д. должны находиться
# при поиске "нет воды", "нет света" и т.д.
WORDS_TO_KEEP = {'нет', 'нetheus', 'нету', 'нетёк'}
RUSSIAN_STOPWORDS = RUSSIAN_STOPWORDS - WORDS_TO_KEEP

print("=" * 70)
print("ИСПРАВЛЕНО (2026-02-18): Список stopwords БЕЗ слова 'нет'")
print(f"Всего stopwords: {len(RUSSIAN_STOPWORDS)} (было 151)")
print(f"Исключены слова: {WORDS_TO_KEEP}")
print("=" * 70)


def preprocess_service(scenario_name: str, category: str, object_name: str, morph: pymorphy2.MorphAnalyzer) -> str:
    """
    Предобработка текста услуги перед векторизацией.
    Собирает строку: "scenario_name category object_name"

    Args:
        scenario_name: Название сценария услуги
        category: Категория услуги
        object_name: Объект услуги
        morph: Морфологический анализатор

    Returns:
        Предобработанный текст для отправки в Yandex Embeddings
    """
    # Собираем components
    components = [scenario_name]
    if category:
        components.append(category)
    if object_name:
        components.append(object_name)

    # Объединяем
    text = ' '.join(components).lower()

    # Разбиваем на слова
    words = text.split()

    # Удаляем stopwords и лемматизируем
    filtered_words = []
    for word in words:
        if word in RUSSIAN_STOPWORDS:
            continue

        # Лемматизация
        parsed = morph.parse(word)[0]
        lemma = parsed.normal_form

        if lemma not in RUSSIAN_STOPWORDS:
            filtered_words.append(lemma)

    # Собираем обратно
    return ' '.join(filtered_words)


async def generate_service_embeddings():
    """Генерация embedding для всех услуг"""

    print("=" * 60)
    print("ГЕНЕРАЦИЯ EMBEDDING ДЛЯ УСЛУГ")
    print("=" * 60)

    # Инициализация
    service = AIAgentService(provider='yandexgpt')
    morph = pymorphy2.MorphAnalyzer()

    # Загружаем услуги из БД
    def load_services():
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    sc.service_id,
                    sc.scenario_name,
                    COALESCE(rc.category_name, '') as category,
                    COALESCE(ro.object_name, '') as object_name
                FROM services_catalog sc
                LEFT JOIN ref_categories rc ON sc.category_id = rc.category_id
                LEFT JOIN ref_objects ro ON sc.object_id = ro.object_id
                WHERE sc.is_active = TRUE
                ORDER BY sc.service_id
            """)
            return cursor.fetchall()

    services = await asyncio.to_thread(load_services)

    print(f"\nЗагружено услуг: {len(services)}")

    if not services:
        print("Нет услуг для обработки")
        return

    # Генерируем embedding для каждой услуги
    success_count = 0
    error_count = 0
    total_cost = 0.0

    for service_id, scenario_name, category, object_name in services:
        try:
            print(f"\n[{service_id}] {scenario_name}")
            print(f"    Категория: {category or 'нет'}")
            print(f"    Объект: {object_name or 'нет'}")

            # Предобработка
            embedding_text = preprocess_service(scenario_name, category, object_name, morph)
            print(f"    Предобработанный текст: '{embedding_text}'")

            if not embedding_text:
                print("    ⚠️ Пустой текст после предобработки - пропускаем")
                continue

            # Получаем embedding
            embedding, usage = await service.get_embedding(embedding_text)

            print(f"    Размерность: {len(embedding)}")
            print(f"    Стоимость: {usage['cost_rub']:.6f} руб.")

            # Сохраняем в БД
            def save_embedding():
                with connection.cursor() as cursor:
                    cursor.execute("""
                        UPDATE services_catalog
                        SET embedding_service = %s::jsonb,
                            embedding_text = %s
                        WHERE service_id = %s
                    """, [str(embedding), embedding_text, service_id])
                    connection.commit()

            await asyncio.to_thread(save_embedding)

            success_count += 1
            total_cost += usage['cost_rub']

            # Небольшая пауза чтобы не перегрузить API
            await asyncio.sleep(0.1)

        except Exception as e:
            error_count += 1
            print(f"    ❌ ОШИБКА: {e}")

    # Итоги
    print("\n" + "=" * 60)
    print("ИТОГИ:")
    print(f"  Успешно: {success_count}/{len(services)}")
    print(f"  Ошибок: {error_count}")
    print(f"  Общая стоимость: {total_cost:.6f} руб.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(generate_service_embeddings())
