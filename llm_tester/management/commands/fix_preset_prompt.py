#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Management команда для исправления кастомного промпта в пресете
Умное экранирование всех фигурных скобок, кроме валидных переменных
"""

from django.core.management.base import BaseCommand
from llm_tester.models import PromptPreset
import re


class Command(BaseCommand):
    help = 'Исправляет фигурные скобки в кастомном промпте пресета'

    def handle(self, *args, **options):
        try:
            preset = PromptPreset.objects.get(id=4)
            if not preset.custom_prompt:
                self.stdout.write(self.style.WARNING('У пресета нет кастомного промпта'))
                return

            original = preset.custom_prompt

            # Список валидных переменных в этом промпте
            valid_vars = {'txt_prb', 'categories', 'history'}

            # Функция для экранирования фигурных скобок
            def escape_braces_except_valid(text):
                result = []
                i = 0
                while i < len(text):
                    if text[i] == '{':
                        # Проверяем, является ли это валидной переменной
                        # Извлекаем потенциальное имя переменной до }
                        j = i + 1
                        var_name = ''
                        while j < len(text) and text[j] != '}':
                            if text[j].isalnum() or text[j] == '_':
                                var_name += text[j]
                                j += 1
                            else:
                                # Если встретили не-букву/цифру/_, это не валидная переменная
                                break

                        # Если нашли } и var_name в списке валидных - оставляем как есть
                        if j < len(text) and text[j] == '}' and var_name in valid_vars:
                            result.append(text[i:j+1])  # Оставляем {varname}
                            i = j + 1
                        else:
                            # Не валидная переменная - экранируем скобку
                            result.append('{{')
                            i += 1
                    elif text[i] == '}':
                        # Экранируем закрывающую скобку
                        result.append('}}')
                        i += 1
                    else:
                        result.append(text[i])
                        i += 1
                return ''.join(result)

            fixed = escape_braces_except_valid(original)

            # Сохраняем исправленный промпт
            if fixed != original:
                preset.custom_prompt = fixed
                preset.save()
                self.stdout.write(self.style.SUCCESS(f'Промпт пресета "{preset.name}" исправлен!'))
                self.stdout.write(f'Было: {len(original)} символов')
                self.stdout.write(f'Стало: {len(fixed)} символов')

                # Проверяем, что теперь format() работает
                test_vars = {
                    'txt_prb': 'тест',
                    'categories': 'Водоснабжение, Отопление',
                    'history': ''
                }
                try:
                    result = fixed.format(**test_vars)
                    self.stdout.write(self.style.SUCCESS('✓ Проверка format() прошла успешно!'))
                    self.stdout.write(f'✓ Длина результата после подстановки: {len(result)}')
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f'✗ Ошибка format(): {e}'))
            else:
                self.stdout.write(self.style.WARNING('Промпт не требует исправлений'))

        except PromptPreset.DoesNotExist:
            self.stdout.write(self.style.ERROR('Пресет с ID=4 не найден'))
