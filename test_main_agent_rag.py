#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тестирование нового промта Main Agent (RAG Universal) на реальных запросах
"""

import os
import django
import json
import asyncio
from datetime import datetime

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
django.setup()

from ai_agent_service import AIAgentService
from llm_tester.models import PromptTemplate


class MainAgentTester:
    """Тестер Main Agent"""

    def __init__(self):
        self.ai_service = AIAgentService()
        self.test_cases = self._load_test_cases()
        # Получаем промт сразу в синхронном контексте
        self.prompt_template = self.get_prompt_template()

    def _load_test_cases(self):
        """Загрузка тестовых случаев"""
        return [
            {
                "name": "Течет труба в ванной",
                "messages": [
                    {"role": "user", "text": "Привет"},
                    {"role": "assistant", "text": "Здравствуйте! Чем могу помочь?"},
                    {"role": "user", "text": "У меня течет труба в ванной"}
                ],
                "expected": "Должен определить OBJ=труба, EVENT=течет, PLACE=ванная"
            },
            {
                "name": "Прорыв батареи",
                "messages": [
                    {"role": "user", "text": "Привет"},
                    {"role": "assistant", "text": "Здравствуйте! Готов помочь."},
                    {"role": "user", "text": "Помогите, у меня прорвало батарею, вода везде"}
                ],
                "expected": "Должен определить категорию Отопление, срочность высокая"
            },
            {
                "name": "Не работает лифт",
                "messages": [
                    {"role": "user", "text": "Лифт не работает, застрял между этажами"}
                ],
                "expected": "Должен определить OBJ=лифт, PLACE=подъезд"
            },
            {
                "name": "Запах газа",
                "messages": [
                    {"role": "user", "text": "Пахнет газом в квартире, что делать?"}
                ],
                "expected": "Должен сработать safety-check, дать инструкции по эвакуации"
            },
            {
                "name": "Уличное освещение",
                "messages": [
                    {"role": "user", "text": "Во дворе не горит фонарь уже три дня"}
                ],
                "expected": "Должен определить PLACE=двор,_OBJ=фонарь"
            },
            {
                "name": "Многовариантный запрос (неоднозначность)",
                "messages": [
                    {"role": "user", "text": "Кран"},
                    {"role": "assistant", "text": "Здравствуйте! Что случилось с краном?"},
                    {"role": "user", "text": "Течет"}
                ],
                "expected": "Должен задать вопрос про локацию (кухня/ванная)"
            },
            {
                "name": "Агрессивный пользователь",
                "messages": [
                    {"role": "user", "text": "Вы опять ничего не делаете! Я уже неделю жду!"}
                ],
                "expected": "Должен сработать NEGATIVE mode, эмпатия + контроль"
            },
            {
                "name": "Уточнение адреса",
                "messages": [
                    {"role": "user", "text": "Прорвало трубу"},
                    {"role": "assistant", "text": "Понял, прорыв трубы. Где именно это произошло?"},
                    {"role": "user", "text": "На кухне"}
                ],
                "expected": "Должен продолжить сбор адреса"
            }
        ]

    def get_prompt_template(self):
        """Получить шаблон промта"""
        tmpl = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()
        if not tmpl:
            raise ValueError("Промт mainagent-orchestrator не найден")
        return tmpl.template

    def format_dialog_history(self, messages):
        """Форматировать историю диалога"""
        formatted = []
        for msg in messages:
            role = "Пользователь" if msg['role'] == 'user' else "Ассистент"
            formatted.append(f"{role}: {msg['text']}")
        return "\n".join(formatted)

    def format_prompt(self, template, variables):
        """Форматирует шаблон промта с переменными"""
        prompt = template

        # Заменяем переменные
        for key, value in variables.items():
            placeholder = f'{{{{{key}}}}}'
            if placeholder in prompt:
                prompt = prompt.replace(placeholder, str(value))

        return prompt

    async def test_single_case(self, test_case):
        """Тест одного случая"""
        print(f"\n{'='*80}")
        print(f"ТЕСТ: {test_case['name']}")
        print(f"{'='*80}")

        # Показываем входные данные
        print("\n📥 ВХОДНЫЕ ДАННЫЕ:")
        print(self.format_dialog_history(test_case['messages']))

        print(f"\n📋 ОЖИДАЕМОЕ: {test_case['expected']}")

        try:
            # Формируем запрос
            last_message = test_case['messages'][-1]['text']
            context = self.format_dialog_history(test_case['messages'][:-1])

            # Подготавливаем переменные для шаблона
            variables = {
                'message_text': last_message,
                'context': context,
                'txtPrb': '{}',  # Пустой JSON для начала
                'established_filters_json': '{}',
                'KNOWLEDGE_BASE': '',
                'SERVICE_CATALOG': '- #Сантехника #Водоснабжение #Канализация #Отопление #Батарея #Радиатор\n- #Электроснабжение #Электрика #Свет\n- #Газоснабжение #Газ #Плита\n- #Лифт #Мусоропровод #Домофон\n- #Окна #Двери #Балкон #Лоджия\n- #Кровля #Фасад #Крыша\n- #Двор #Детская #Площадка #Парковка\n- #Подвал #Подпол\n- #Кондиционер #Сплит-система\n- #Прочее'
            }

            # Используем уже загруженный шаблон
            template = self.prompt_template

            # Форматируем промт
            formatted_prompt = self.format_prompt(template, variables)

            # Отладочный вывод (первые 1000 символов)
            print("\n📄 ФОРМАТИРОВАННЫЙ ПРОМТ (первые 1000 символов):")
            print("-" * 80)
            print(formatted_prompt[:1000])
            print("..." if len(formatted_prompt) > 1000 else "")
            print("-" * 80)

            # Вызываем AI
            print("\n🤖 ВЫЗОВ AI...")
            response, usage = await self.ai_service.call_llm(
                prompt=formatted_prompt,
                provider="yandexgpt",
                temperature=0.3,
                max_tokens=500
            )

            print("\n✅ ОТВЕТ AI:")
            print("-" * 80)
            print(response)
            print("-" * 80)

            # Информация о стоимости
            print(f"\n💰 СТОИМОСТЬ: {usage.get('cost_rub', 0):.4f} руб.")
            print(f"   Токенов: {usage.get('total_tokens', 0)} (вход: {usage.get('input_tokens', 0)}, выход: {usage.get('output_tokens', 0)})")

            # Анализ ответа
            self._analyze_response(response, test_case)

            return {
                'name': test_case['name'],
                'success': True,
                'response': response
            }

        except Exception as e:
            print(f"\n❌ ОШИБКА: {str(e)}")
            import traceback
            traceback.print_exc()

            return {
                'name': test_case['name'],
                'success': False,
                'error': str(e)
            }

    def _analyze_response(self, response, test_case):
        """Анализ ответа AI"""
        print("\n🔊 АНАЛИЗ ОТВЕТА:")

        # Проверка на вопросы
        question_count = response.count('?')
        print(f"   - Количество вопросов: {question_count}")

        # Проверка длины
        words = response.split()
        print(f"   - Длина ответа: {len(words)} слов")

        # Проверка на эмодзи
        has_emoji = any(ord(char) > 127 for char in response)
        print(f"   - Содержит эмодзи: {'Да ❌' if has_emoji else 'Нет ✅'}")

        # Проверка на открытые вопросы
        if question_count > 0:
            # Простая эвристика для закрытых вопросов
            closed_keywords = ['да', 'нет', 'хотите', 'можете', 'будете', 'хочешь', 'можешь']
            is_closed = any(keyword in response.lower() for keyword in closed_keywords)
            print(f"   - Тип вопроса: {'Закрытый ❌' if is_closed else 'Открытый ✅'}")

        # Проверка на эмпатию
        empathy_keywords = ['понял', 'понимаю', 'сожалею', 'признаю', 'вижу', 'слышу']
        has_empathy = any(keyword in response.lower() for keyword in empathy_keywords)
        print(f"   - Есть эмпатия: {'Да ✅' if has_empathy else 'Нет ⚠️'}")

    async def run_all_tests(self):
        """Запуск всех тестов"""
        print("="*80)
        print("ТЕСТИРОВАНИЕ MAIN AGENT (RAG UNIVERSAL)")
        print(f"Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)

        results = []

        for i, test_case in enumerate(self.test_cases, 1):
            print(f"\n\n[{i}/{len(self.test_cases)}] ", end="")
            result = await self.test_single_case(test_case)
            results.append(result)

        # Итого
        self._print_summary(results)

        return results

    def _print_summary(self, results):
        """Вывод итогов"""
        print("\n\n")
        print("="*80)
        print("ИТОГИ ТЕСТИРОВАНИЯ")
        print("="*80)

        success_count = sum(1 for r in results if r['success'])
        total_count = len(results)

        print(f"\nВсего тестов: {total_count}")
        print(f"Успешно: {success_count}")
        print(f"Ошибок: {total_count - success_count}")
        print(f"Успешность: {success_count/total_count*100:.1f}%")

        print("\n📊 Результаты по тестам:")
        for result in results:
            status = "✅" if result['success'] else "❌"
            print(f"   {status} {result['name']}")
            if not result['success']:
                print(f"      Ошибка: {result.get('error', 'Неизвестно')}")


async def main():
    """Главная функция"""
    tester = MainAgentTester()
    await tester.run_all_tests()


if __name__ == '__main__':
    asyncio.run(main())
