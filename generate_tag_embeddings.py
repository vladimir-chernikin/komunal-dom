#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Генерация embedding для тегов из ref_tags
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


def preprocess_tag(tag_name: str, morph: pymorphy2.MorphAnalyzer) -> str:
    """
    Предобработка тега перед векторизацией:
    1. Нижний регистр
    2. Удаление stopwords
    3. Лемматизация pymorphy2

    Args:
        tag_name: Исходный текст тега
        morph: Морфологический анализатор

    Returns:
        Предобработанный текст для отправки в Yandex Embeddings
    """
    # Приводим к нижнему регистру
    text = tag_name.lower()

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


async def generate_tag_embeddings():
    """Генерация embedding для всех тегов"""

    print("=" * 60)
    print("ГЕНЕРАЦИЯ EMBEDDING ДЛЯ ТЕГОВ")
    print("=" * 60)

    # Инициализация
    service = AIAgentService(provider='yandexgpt')
    morph = pymorphy2.MorphAnalyzer()

    # Загружаем теги из БД
    def load_tags():
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT tag_id, tag_name
                FROM ref_tags
                WHERE is_active = TRUE
                ORDER BY tag_id
            """)
            return cursor.fetchall()

    tags = await asyncio.to_thread(load_tags)

    print(f"\nЗагружено тегов: {len(tags)}")

    if not tags:
        print("Нет тегов для обработки")
        return

    # Генерируем embedding для каждого тега
    success_count = 0
    error_count = 0
    total_cost = 0.0

    for tag_id, tag_name in tags:
        try:
            print(f"\n[{tag_id}] {tag_name}")

            # Предобработка
            embedding_text = preprocess_tag(tag_name, morph)
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
                        UPDATE ref_tags
                        SET embedding_tag = %s::jsonb,
                            embedding_text = %s
                        WHERE tag_id = %s
                    """, [str(embedding), embedding_text, tag_id])
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
    print(f"  Успешно: {success_count}/{len(tags)}")
    print(f"  Ошибок: {error_count}")
    print(f"  Общая стоимость: {total_cost:.6f} руб.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(generate_tag_embeddings())
