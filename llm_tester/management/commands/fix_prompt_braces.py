#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Management команда для исправления промптов - экранирование фигурных скобок
"""

from django.core.management.base import BaseCommand
from llm_tester.models import PromptTemplate
import re


class Command(BaseCommand):
    help = 'Экранирует фигурные скобки в промптах, которые не являются переменными'

    def handle(self, *args, **options):
        templates = PromptTemplate.objects.all()

        for template in templates:
            original = template.template
            fixed = original

            # Находим все "валидные" переменные (формат {word})
            valid_vars = set(re.findall(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}', fixed))

            # Заменяем все {{ и }} на временные маркеры
            fixed = fixed.replace('{{', '<<<DOUBLE_LEFT>>>')
            fixed = fixed.replace('}}', '<<<DOUBLE_RIGHT>>>')

            # Экранируем фигурные скобки, которые НЕ являются валидными переменными
            def replace_braces(match):
                brace_content = match.group(1)
                # Если это валидная переменная - не экранируем
                if brace_content in valid_vars:
                    return match.group(0)
                # Иначе экранируем
                return '{{' + brace_content + '}}'

            # Заменяем {something} на {something}, если something не валидная переменная
            fixed = re.sub(r'\{([^}]+)\}', replace_braces, fixed)

            # Восстанавливаем удвоенные скобки
            fixed = fixed.replace('<<<DOUBLE_LEFT>>>', '{{')
            fixed = fixed.replace('<<<DOUBLE_RIGHT>>>', '}}')

            if fixed != original:
                self.stdout.write(self.style.SUCCESS(f'Исправляем шаблон: {template.name}'))
                template.template = fixed
                template.save()
                self.stdout.write(f'  Было: {len(original)} символов')
                self.stdout.write(f'  Стало: {len(fixed)} символов')
            else:
                self.stdout.write(self.style.WARNING(f'Шаблон {template.name} не требует исправлений'))

        self.stdout.write(self.style.SUCCESS('\nГотово!'))
