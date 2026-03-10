#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Management команда для исправления FilterDetectionService промпта
"""

from django.core.management.base import BaseCommand
from llm_tester.models import PromptTemplate


class Command(BaseCommand):
    help = 'Исправляет фигурные скобки в FilterDetectionService промпте'

    def handle(self, *args, **options):
        try:
            template = PromptTemplate.objects.get(slug='filter-detection-service')
            original = template.template

            # Заменяем удвоенные фигурные скобки на учетверенные
            # {{ -> {{{{
            # }} -> }}}}
            fixed = original.replace('{{', '{{{{').replace('}}', '}}}}')

            if fixed != original:
                template.template = fixed
                template.save()
                self.stdout.write(self.style.SUCCESS(f'Промпт {template.name} исправлен!'))
                self.stdout.write(f'Количество замен: {fixed.count("{{{{")}')
            else:
                self.stdout.write(self.style.WARNING('Промпт не требует исправлений'))

        except PromptTemplate.DoesNotExist:
            self.stdout.write(self.style.ERROR('Промпт FilterDetectionService не найден'))
