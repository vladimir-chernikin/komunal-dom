#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Детальная отладка VectorSearchService для service_id=27
"""

import os
import sys
import django
import asyncio
import numpy as np
from asgiref.sync import sync_to_async

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
sys.path.insert(0, '/var/www/komunal-dom_ru')
django.setup()

from vector_search_service import VectorSearchService


async def debug_service_27():
    """Детальная отладка service_id=27"""

    txtPrb = "у пользователя течёт из трубы"

    vector_service = VectorSearchService()

    print("=" * 80)
    print("ОТЛАДКА SERVICE_ID=27")
    print("=" * 80)

    # Получаем embedding запроса
    from ai_agent_service import AIAgentService
    ai_service = AIAgentService(provider='yandexgpt')
    message_clean = vector_service._preprocess_text(txtPrb)
    query_embedding, _ = await ai_service.get_embedding(message_clean)
    query_embedding = np.array(query_embedding, dtype=np.float32)

    print(f"Query: '{message_clean}'")
    print(f"Query embedding shape: {query_embedding.shape}")
    print()

    # Проверяем embedding услуги 27
    from django.db import connection

    def check_service_27():
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT service_id, scenario_name, embedding_service, embedding_text
                FROM services_catalog
                WHERE service_id = 27
            """)
            return cursor.fetchone()

    row = await sync_to_async(check_service_27)()
    service_id, scenario_name, embedding_json, embedding_text = row

    print(f"Service ID: {service_id}")
    print(f"Name: {scenario_name}")
    print(f"Embedding text: {embedding_text}")
    print()

    # Парсим embedding
    try:
        service_embedding = np.array(eval(embedding_json), dtype=np.float32)
        print(f"Service embedding shape: {service_embedding.shape}")
    except:
        print("❌ Ошибка парсинга embedding!")
        return

    # Вычисляем косинусное сходство
    similarity = vector_service._cosine_similarity(query_embedding, service_embedding)

    print(f"Cosine similarity: {similarity:.4f}")
    print()

    # Проверяем в каком поиске найдено
    print("ПРОВЕРКА В _SEARCH_BY_TAGS:")

    def search_by_tags():
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT rt.tag_name, rt.embedding_tag
                FROM ref_tags rt
                JOIN service_tags st ON rt.tag_id = st.tag_id
                WHERE st.service_id = 27 AND rt.is_active = TRUE
                LIMIT 10
            """)
            return cursor.fetchall()

    tags = await sync_to_async(search_by_tags)()

    print(f"Теги услуги 27:")
    for tag_name, tag_embedding in tags:
        if tag_embedding:
            try:
                tag_emb = np.array(eval(tag_embedding), dtype=np.float32)
                tag_sim = vector_service._cosine_similarity(query_embedding, tag_emb)
                print(f"  - {tag_name}: similarity={tag_sim:.4f}")
            except:
                pass
    print()

    # Полный поиск через VectorSearch
    print("ПОЛНЫЙ ПОИСК ЧЕРЕЗ VECTORSEARCH:")
    result = await vector_service.search(
        message_text=txtPrb,
        filters={'category': {'value': 'Водоснабжение', 'confidence': 0.9}}
    )

    for c in result.get('candidates', []):
        if c.get('service_id') == 27:
            print(f"Найден кандидат service_id=27:")
            print(f"  confidence: {c.get('confidence')}")
            print(f"  source: {c.get('source')}")
            print(f"  tag_confidence: {c.get('tag_confidence')}")
            print(f"  service_confidence: {c.get('service_confidence')}")
            return

    print("❌ Service 27 НЕ найден в кандидатах!")


if __name__ == '__main__':
    asyncio.run(debug_service_27())
