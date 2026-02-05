#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Management команда для добавления комментария "ВЧ:Рефакторинг 05.02.2026" во все промпты
"""

from django.core.management.base import BaseCommand
from llm_tester.models import PromptTemplate


class Command(BaseCommand):
    help = 'Добавляет комментарий "ВЧ:Рефакторинг 05.02.2026" во все промпты'

    def handle(self, *args, **options):
        # Список slug'ов промптов для обновления
        slugs = [
            'problem-accumulation-service',
            'filter-incident-type',
            'filter-location-type',
            'filter-category',
            'mainagent-clarify-category',
            'mainagent-validate-question',
            'mainagent-orchestrator',
        ]

        comment = "# ВЧ:Рефакторинг 05.02.2026"

        updated_count = 0
        not_found_count = 0

        for slug in slugs:
            try:
                prompt = PromptTemplate.objects.get(slug=slug)

                # Проверяем есть ли уже комментарий
                if prompt.template.startswith(comment):
                    self.stdout.write(self.style.WARNING(f'⚠️  {slug} - комментарий уже есть'))
                    continue

                # Добавляем комментарий первой строкой
                old_template = prompt.template
                new_template = f"{comment}\n{old_template}"

                prompt.template = new_template
                prompt.save()

                updated_count += 1
                self.stdout.write(self.style.SUCCESS(f'✅ {slug} - комментарий добавлен'))

            except PromptTemplate.DoesNotExist:
                not_found_count += 1
                self.stdout.write(self.style.ERROR(f'❌ {slug} - НЕ НАЙДЕН'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'❌ {slug} - ошибка: {e}'))

        # Итог
        self.stdout.write(self.style.SUCCESS('\n' + '=' * 80))
        self.stdout.write(self.style.SUCCESS('ИТОГИ ОБНОВЛЕНИЯ:'))
        self.stdout.write(self.style.SUCCESS(f'  ✅ Обновлено: {updated_count}'))
        self.stdout.write(self.style.WARNING(f'  ⚠️  Уже имели комментарий: 0'))
        self.stdout.write(self.style.ERROR(f'  ❌ Не найдено: {not_found_count}'))
        self.stdout.write(self.style.SUCCESS('=' * 80))
