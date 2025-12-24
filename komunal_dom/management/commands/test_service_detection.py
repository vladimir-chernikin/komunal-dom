#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тест системы определения услуг через Django management command
"""

from django.core.management.base import BaseCommand
import asyncio
from main_agent import MainAgent
import json

class Command(BaseCommand):
    help = 'Тест полной системы определения услуг'

    def handle(self, *args, **options):
        async def test_system():
            # Инициализация MainAgent
            agent = MainAgent()

            # Тестовые запросы
            test_queries = [
                "открылась течь",
                "с крыши",
                "протекает крыша",
                "крыша течет",
                "какая погода"
            ]

            results = []

            for i, query in enumerate(test_queries, 1):
                self.stdout.write(f"\n📍 Тест {i}: '{query}'")
                self.stdout.write("-" * 30)

                result = await agent.process_service_detection(query)

                self.stdout.write(f"Статус: {result.get('status')}")
                self.stdout.write(f"Сообщение: {result.get('message')}")
                self.stdout.write(f"Найдено кандидатов: {len(result.get('candidates', []))}")

                for j, candidate in enumerate(result.get('candidates', []), 1):
                    self.stdout.write(f"  {j}. [ID:{candidate.get('service_id')}] {candidate.get('service_name')} ({candidate.get('confidence', 0):.3f})")

                results.append({
                    'query': query,
                    'status': result.get('status'),
                    'candidates_count': len(result.get('candidates', []))
                })

            # Итоги
            self.stdout.write("\n📊 Итоги тестов")
            self.stdout.write("=" * 50)

            success_count = sum(1 for r in results if r['status'] in ['SUCCESS', 'AMBIGUOUS'])

            for result in results:
                status = "✅ OK" if result['status'] in ['SUCCESS', 'AMBIGUOUS'] else "❌ FAIL"
                self.stdout.write(f"{result['query']}: {status} ({result['status']}) - {result['candidates_count']} кандидатов")

            self.stdout.write(f"\nРезультат: {success_count}/{len(test_queries)} тестов успешно")

        # Запуск асинхронного теста
        asyncio.run(test_system())