#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Management команда для правильного исправления FilterDetectionService промпта
"""

from django.core.management.base import BaseCommand
from llm_tester.models import PromptTemplate


class Command(BaseCommand):
    help = 'Правильно исправляет фигурные скобки в FilterDetectionService промпте'

    def handle(self, *args, **options):
        try:
            template = PromptTemplate.objects.get(slug='filter-detection-service')
            current = template.template

            # Возвращаем обратно {{{{ -> {{
            reverted = current.replace('{{{{', '{{').replace('}}}}', '}}')

            # Теперь заменяем конкретные проблемные места
            # Все JSON структуры и множества нужно экранировать

            # Замены для множеств
            replacements = [
                ('SET_EVENT = {{ (cat, p_event[cat]) }}', 'SET_EVENT = {{{{ (cat, p_event[cat]) }}}}'),
                ('SET_PLACE = {{ (cat, p_place[cat]) }}', 'SET_PLACE = {{{{ (cat, p_place[cat]) }}}}'),
                ('SET_OBJ = {{ (cat, p_obj[cat]) }}', 'SET_OBJ = {{{{ (cat, p_obj[cat]) }}}}'),
            ]

            fixed = reverted
            for old, new in replacements:
                fixed = fixed.replace(old, new)

            if fixed != reverted:
                template.template = fixed
                template.save()
                self.stdout.write(self.style.SUCCESS(f'Промпт {template.name} исправлен!'))
                for old, new in replacements:
                    if old in reverted:
                        self.stdout.write(f'  Заменено: {old[:50]}...')
            else:
                self.stdout.write(self.style.WARNING('Замены не применены - возможно уже исправлено'))

        except PromptTemplate.DoesNotExist:
            self.stdout.write(self.style.ERROR('Промпт FilterDetectionService не найден'))
