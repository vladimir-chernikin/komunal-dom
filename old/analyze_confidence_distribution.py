#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Анализ распределения confidence в реальных диалогах

ЦЕЛЬ: Понять какое распределение confidence у фильтров в реальных диалогах
      чтобы решить правильные ли пороги 0.90 vs 0.60/0.70/0.80

ДАТА: 2026-02-14
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

import psycopg2
from django.conf import settings
from collections import defaultdict
import json

def get_confidence_distribution():
    """Получает распределение confidence из dialog_logs"""

    db_settings = settings.DATABASES['default']

    conn = psycopg2.connect(
        host=db_settings['HOST'],
        database=db_settings['NAME'],
        user=db_settings['USER'],
        password=db_settings['PASSWORD'],
        port=db_settings.get('PORT', 5432)
    )

    try:
        with conn.cursor() as cursor:
            # Получаем последние диалоги с установленными фильтрами
            query = """
                SELECT
                    session_id,
                    channel,
                    timestamp,
                    metadata
                FROM dialog_logs
                WHERE metadata IS NOT NULL
                  AND metadata ? 'filters'
                ORDER BY timestamp DESC
                LIMIT 100
            """

            cursor.execute(query)
            rows = cursor.fetchall()

            print(f"\n📊 НАЙДЕНО {len(rows)} диалогов с фильтрами")
            print("=" * 80)

            # Собираем статистику
            incident_conf = []
            location_conf = []
            category_conf = []

            for session_id, channel, timestamp, metadata in rows:
                try:
                    meta = json.loads(metadata) if isinstance(metadata, str) else metadata

                    if 'filters' in meta:
                        filters = meta['filters']

                        # incident_type
                        if 'incident_type' in filters:
                            incident = filters['incident_type']
                            if isinstance(incident, dict):
                                conf = incident.get('confidence', 0)
                                if conf > 0:
                                    incident_conf.append(conf)

                        # location_type
                        if 'location_type' in filters:
                            location = filters['location_type']
                            if isinstance(location, dict):
                                conf = location.get('confidence', 0)
                                if conf > 0:
                                    location_conf.append(conf)

                        # category
                        if 'category' in filters:
                            cat = filters['category']
                            if isinstance(cat, dict):
                                conf = cat.get('confidence', 0)
                                if conf > 0:
                                    category_conf.append(conf)

                except Exception as e:
                    print(f"Ошибка парсинга metadata для {session_id}: {e}")
                    continue

            # Анализируем распределение
            print("\n🔍 РАСПРЕДЕЛЕНИЕ CONFIDENCE ПО ФИЛЬТРАМ:")
            print("=" * 80)

            analyze_confidence('incident_type', incident_conf, threshold=0.70)
            analyze_confidence('location_type', location_conf, threshold=0.80)
            analyze_confidence('category', category_conf, threshold=0.60)

            # Сравниваем с порогом 0.90
            print("\n📊 СРАВНЕНИЕ С ПОРОГОМ 0.90:")
            print("=" * 80)

            print("\n1. INCIDENT_TYPE:")
            if incident_conf:
                above_90 = sum(1 for c in incident_conf if c >= 0.90)
                below_90 = len(incident_conf) - above_90
                print(f"   >= 0.90: {above_90} ({above_90/len(incident_conf)*100:.1f}%)")
                print(f"   < 0.90: {below_90} ({below_90/len(incident_conf)*100:.1f}%)")
                print(f"   Если порог 0.90: {below_90} фильтров будут ИГНОРИРОВАТЬСЯ")

            print("\n2. LOCATION_TYPE:")
            if location_conf:
                above_90 = sum(1 for c in location_conf if c >= 0.90)
                below_90 = len(location_conf) - above_90
                print(f"   >= 0.90: {above_90} ({above_90/len(location_conf)*100:.1f}%)")
                print(f"   < 0.90: {below_90} ({below_90/len(location_conf)*100:.1f}%)")
                print(f"   Если порог 0.90: {below_90} фильтров будут ИГНОРИРОВАТЬСЯ")

            print("\n3. CATEGORY:")
            if category_conf:
                above_90 = sum(1 for c in category_conf if c >= 0.90)
                below_90 = len(category_conf) - above_90
                print(f"   >= 0.90: {above_90} ({above_90/len(category_conf)*100:.1f}%)")
                print(f"   < 0.90: {below_90} ({below_90/len(category_conf)*100:.1f}%)")
                print(f"   Если порог 0.90: {below_90} фильтров будут ИГНОРИРОВАТЬСЯ")

            # Гистограммы
            print("\n📈 ГИСТОГРАММЫ:")
            print("=" * 80)

            if incident_conf:
                print_histogram('incident_type', incident_conf, bins=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

            if location_conf:
                print_histogram('location_type', location_conf, bins=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

            if category_conf:
                print_histogram('category', category_conf, bins=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

    finally:
        conn.close()


def analyze_confidence(filter_name: str, confidences: list, threshold: float):
    """Анализирует confidence для одного фильтра"""

    if not confidences:
        print(f"\n❌ {filter_name}: нет данных")
        return

    confidences.sort()

    print(f"\n📌 {filter_name} (всего {len(confidences)} значений):")
    print(f"   Минимум: {min(confidences):.2f}")
    print(f"   Максимум: {max(confidences):.2f}")
    print(f"   Среднее: {sum(confidences)/len(confidences):.2f}")
    print(f"   Медиана: {confidences[len(confidences)//2]:.2f}")

    # Процент выше порога
    above_threshold = sum(1 for c in confidences if c >= threshold)
    print(f"   >= {threshold}: {above_threshold} ({above_threshold/len(confidences)*100:.1f}%)")
    print(f"   < {threshold}: {len(confidences) - above_threshold} ({(len(confidences) - above_threshold)/len(confidences)*100:.1f}%)")


def print_histogram(filter_name: str, confidences: list, bins: list):
    """Печатает гистограмму"""

    print(f"\n📊 {filter_name}:")

    for i in range(len(bins) - 1):
        lower = bins[i]
        upper = bins[i + 1]

        count = sum(1 for c in confidences if lower <= c < upper)
        percentage = count / len(confidences) * 100 if confidences else 0

        bar = '█' * int(percentage / 2)
        print(f"   [{lower:.1f} - {upper:.1f}): {count:3d} ({percentage:5.1f}%) {bar}")

    # Последний бакет (точно 1.0)
    count_100 = sum(1 for c in confidences if c == 1.0)
    if count_100 > 0:
        percentage = count_100 / len(confidences) * 100
        bar = '█' * int(percentage / 2)
        print(f"   [1.0        : {count_100:3d} ({percentage:5.1f}%) {bar}")


if __name__ == '__main__':
    print("\n" + "🔬" * 40)
    print("АНАЛИЗ РАСПРЕДЕЛЕНИЯ CONFIDENCE В РЕАЛЬНЫХ ДИАЛОГАХ")
    print("🔬" * 40)

    get_confidence_distribution()

    print("\n" + "=" * 80)
    print("💡 ВЫВОДЫ:")
    print("=" * 80)
    print("""
1. Если большая часть confidence >= 0.90:
   → Порог 0.90 ПОДХОДИТ (консервативный, мало false positives)

2. Если большая часть confidence между 0.60-0.89:
   → Порог 0.90 СЛИШКОМ СТРОГИЙ (много false negatives)
   → НУЖНО СНИЗИТЬ до 0.70 или 0.80

3. Если распределение равномерное:
   → Нужны разные пороги для разных фильтров (как в MainAgent)
    """)
