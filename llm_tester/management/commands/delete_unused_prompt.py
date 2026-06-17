#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Management команда для удаления неиспользуемого промпта
"""

from django.core.management.base import BaseCommand
from llm_tester.models import PromptTemplate


class Command(BaseCommand):
    help = 'Удаляет неиспользуемый промпт MainAgent (ID: 2, slug: main-agent)'

    def handle(self, *args, **options):
        slug = 'main-agent'

        try:
            prompt = PromptTemplate.objects.get(slug=slug)

            self.stdout.write(self.style.WARNING(f'⚠️  НАЙДЕН НЕИСПОЛЬЗУЕМЫЙ ПРОМПТ:'))
            self.stdout.write(f'  ID: {prompt.id}')
            self.stdout.write(f'  Название: {prompt.name}')
            self.stdout.write(f'  Slug: {prompt.slug}')
            self.stdout.write(f'  Тип: {prompt.prompt_type}')
            self.stdout.write(f'  Создан: {prompt.created_at}')
            self.stdout.write(f'  Обновлен: {prompt.updated_at}')
            self.stdout.write()
            self.stdout.write('ПРИЧИНА УДАЛЕНИЯ:')
            self.stdout.write('  - НЕ загружается в коде (нет запросов по slug="main-agent")')
            self.stdout.write('  - Заменен на 3 новых промпта:')
            self.stdout.write('    * mainagent-clarify-category (ID: 7)')
            self.stdout.write('    * mainagent-validate-question (ID: 8)')
            self.stdout.write('    * mainagent-orchestrator (ID: 9)')
            self.stdout.write()

            # Удаляем
            prompt_id = prompt.id
            prompt.delete()

            self.stdout.write(self.style.SUCCESS(f'✅ Промпт {slug} (ID: {prompt_id}) УДАЛЕН'))

        except PromptTemplate.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'❌ Промпт {slug} не найден'))
