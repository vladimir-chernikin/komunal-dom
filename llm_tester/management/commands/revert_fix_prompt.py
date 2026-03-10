#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Management команда для возврата и правильного исправления FilterDetectionService промпта
"""

from django.core.management.base import BaseCommand
from llm_tester.models import PromptTemplate
import re


class Command(BaseCommand):
    help = 'Правильно исправляет фигурные скобки в FilterDetectionService промпте'

    def handle(self, *args, **options):
        try:
            template = PromptTemplate.objects.get(slug='filter-detection-service')
            current = template.template

            # Сначала вернем обратно {{{{ -> {{
            reverted = current.replace('{{{{', '{{').replace('}}}}', '}}')

            # Теперь правильно экранируем: заменяем все { и } на {{ и }},
            # КРОМЕ тех, что являются реальными переменными

            # Список реальных переменных в промпте
            valid_vars = {'txt_prb', 'categories', 'history'}

            # Функция для замены фигурных скобок
            def escape_braces(text):
                result = []
                i = 0
                while i < len(text):
                    if text[i] == '{' and i + 1 < len(text):
                        # Проверяем, является ли это переменной
                        # Извлекаем потенциальное имя переменной
                        j = i + 1
                        var_name = ''
                        while j < len(text) and text[j] != '}':
                            if text[j].isalnum() or text[j] == '_':
                                var_name += text[j]
                                j += 1
                            else:
                                break

                        if text[j] == '}' and var_name in valid_vars:
                            # Это реальная переменная - оставляем как есть
                            result.append(text[i:j+1])
                            i = j + 1
                        else:
                            # Не переменная - экранируем
                            result.append('{{' + text[i+1:j] + '}}')
                            i = j + 1
                    else:
                        result.append(text[i])
                        i += 1
                return ''.join(result)

            fixed = escape_braces(reverted)

            if fixed != current:
                template.template = fixed
                template.save()
                self.stdout.write(self.style.SUCCESS(f'Промпт {template.name} исправлен!'))
                self.stdout.write(f'Было символов: {len(current)}')
                self.stdout.write(f'Стало символов: {len(fixed)}')
            else:
                self.stdout.write(self.style.WARNING('Промпт не требует исправлений'))

        except PromptTemplate.DoesNotExist:
            self.stdout.write(self.style.ERROR('Промпт FilterDetectionService не найден'))
