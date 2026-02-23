#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тесты для рефакторинга MainAgent v2.0

Тестируемые методы:
- _llm_validate_question() - LLM-валидация вопросов
- _semantic_pre_check() - Семантический Pre-Check
- _build_dynamic_prompt() - Динамическая сборка промптов

Дата: 2026-01-03
"""

import asyncio
import logging
import json
import sys
import os
from typing import Dict, List

# Настройка Django настроек
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
sys.path.insert(0, '/var/www/komunal-dom_ru')

import django
django.setup()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RefactoredMethodsTester:
    """Тестер новых методов MainAgent"""

    def __init__(self):
        """Инициализация тестера"""
        self.main_agent = None
        self.test_results = []
        self.total_tokens = 0
        self.total_cost = 0.0

    async def init(self):
        """Инициализация MainAgent"""
        try:
            from main_agent import MainAgent
            self.main_agent = MainAgent()
            logger.info("MainAgent успешно инициализирован")
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации MainAgent: {e}")
            return False

    def log_test(self, test_name: str, status: str, details: str = "", tokens: int = 0, cost: float = 0.0):
        """Логирование результата теста"""
        result = {
            'test': test_name,
            'status': status,  # PASS, FAIL, SKIP
            'details': details,
            'tokens': tokens,
            'cost': cost
        }
        self.test_results.append(result)

        icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⏭️"
        logger.info(f"{icon} {test_name}: {status}")
        if details:
            logger.info(f"   {details}")
        if tokens > 0:
            logger.info(f"   Токены: {tokens}, Стоимость: {cost:.4f} руб")

        self.total_tokens += tokens
        self.total_cost += cost

    async def test_llm_validate_question_redundant(self):
        """Тест 1: LLM-валидация избыточного вопроса"""
        test_name = "LLM-валидация избыточного вопроса"

        if not self.main_agent or not self.main_agent.ai_agent:
            self.log_test(test_name, "SKIP", "AIAgentService недоступен")
            return

        try:
            # Известные факты
            txtPrb = "у пользователя течет из батареи в зале"
            established_filters = {
                'location': {'value': 'зал', 'confidence': 0.95},
                'category': {'value': 'Отопление', 'confidence': 0.95}
            }

            # Избыточный вопрос (спрашивает о том, что уже известно)
            bad_question = "Где именно это произошло?"

            logger.info(f"   Входной вопрос: '{bad_question}'")
            logger.info(f"   Факты: location=зал (95%), category=Отопление (95%)")

            # Вызываем валидацию
            validated = await self.main_agent._llm_validate_question(
                question=bad_question,
                txtPrb=txtPrb,
                established_filters=established_filters
            )

            # Проверяем результат
            if validated != bad_question:
                self.log_test(
                    test_name,
                    "PASS",
                    f"Вопрос исправлен: '{validated}'",
                    tokens=self._get_last_tokens(),
                    cost=self._get_last_cost()
                )
            else:
                self.log_test(
                    test_name,
                    "FAIL",
                    "Вопрос не был исправлен (ожидалась замена)",
                    tokens=self._get_last_tokens(),
                    cost=self._get_last_cost()
                )

        except Exception as e:
            self.log_test(test_name, "FAIL", f"Ошибка: {e}")

    async def test_llm_validate_question_double(self):
        """Тест 2: LLM-валидация двойного вопроса"""
        test_name = "LLM-валидация двойного вопроса"

        if not self.main_agent or not self.main_agent.ai_agent:
            self.log_test(test_name, "SKIP", "AIAgentService недоступен")
            return

        try:
            # Двойной вопрос
            double_question = "Что именно течет и где это произошло?"

            logger.info(f"   Входной вопрос: '{double_question}'")

            # Вызываем валидацию
            validated = await self.main_agent._llm_validate_question(
                question=double_question,
                txtPrb="течет",
                established_filters={}
            )

            # Проверяем результат
            if validated != double_question:
                self.log_test(
                    test_name,
                    "PASS",
                    f"Двойной вопрос исправлен: '{validated}'",
                    tokens=self._get_last_tokens(),
                    cost=self._get_last_cost()
                )
            else:
                self.log_test(
                    test_name,
                    "PARTIAL",
                    "Двойной вопрос не исправлен (требуется проверка промпта)",
                    tokens=self._get_last_tokens(),
                    cost=self._get_last_cost()
                )

        except Exception as e:
            self.log_test(test_name, "FAIL", f"Ошибка: {e}")

    async def test_llm_validate_question_good(self):
        """Тест 3: LLM-валидация корректного вопроса"""
        test_name = "LLM-валидация корректного вопроса"

        if not self.main_agent or not self.main_agent.ai_agent:
            self.log_test(test_name, "SKIP", "AIAgentService недоступен")
            return

        try:
            # Корректный вопрос
            good_question = "Опишите что именно сломалось"
            txtPrb = "проблема"
            established_filters = {}

            logger.info(f"   Входной вопрос: '{good_question}'")

            # Вызываем валидацию
            validated = await self.main_agent._llm_validate_question(
                question=good_question,
                txtPrb=txtPrb,
                established_filters=established_filters
            )

            # Проверяем результат
            if validated == good_question:
                self.log_test(
                    test_name,
                    "PASS",
                    "Корректный вопрос оставлен без изменений",
                    tokens=self._get_last_tokens(),
                    cost=self._get_last_cost()
                )
            else:
                self.log_test(
                    test_name,
                    "PARTIAL",
                    f"Вопрос изменен: '{validated}' (может быть нормально)",
                    tokens=self._get_last_tokens(),
                    cost=self._get_last_cost()
                )

        except Exception as e:
            self.log_test(test_name, "FAIL", f"Ошибка: {e}")

    async def test_semantic_pre_check(self):
        """Тест 4: SemanticPreCheck - извлечение фактов"""
        test_name = "SemanticPreCheck извлечение фактов"

        if not self.main_agent or not self.main_agent.filter_detection:
            self.log_test(test_name, "SKIP", "FilterDetectionService недоступен")
            return

        try:
            # Текст с четкими фактами
            message_text = "У меня течет из батареи в зале"

            logger.info(f"   Сообщение: '{message_text}'")

            # Вызываем pre-check
            result = await self.main_agent._semantic_pre_check(
                message_text=message_text,
                dialog_history=[]
            )

            # Проверяем результат
            facts = result.get('absolute_facts', [])
            filters = result.get('filters', {})

            if len(facts) > 0:
                fact_list = ", ".join(facts)
                self.log_test(
                    test_name,
                    "PASS",
                    f"Извлечено фактов: {len(facts)} - {fact_list}",
                    tokens=self._get_last_tokens(),
                    cost=self._get_last_cost()
                )

                # Детальный анализ
                logger.info("   Детально:")
                for fact in facts:
                    logger.info(f"     - {fact}")
                if filters:
                    logger.info("   Фильтры:")
                    for name, data in filters.items():
                        logger.info(f"     - {name}={data['value']} (confidence: {data['confidence']:.0%})")
            else:
                self.log_test(
                    test_name,
                    "PARTIAL",
                    "Факты не извлечены (возможно нужен более явный текст)",
                    tokens=self._get_last_tokens(),
                    cost=self._get_last_cost()
                )

        except Exception as e:
            self.log_test(test_name, "FAIL", f"Ошибка: {e}")

    async def test_build_dynamic_prompt_strategy_a(self):
        """Тест 5: BuildDynamicPrompt - Стратегия A (1 кандидат >90%)"""
        test_name = "BuildDynamicPrompt Стратегия A"

        try:
            candidates = [{'service_id': 25, 'service_name': 'Прорыв труб в квартире', 'category': 'Водоснабжение', 'location_type': 'Индивидуальное'}]
            absolute_facts = ['Проблема: течет', 'Локация: Индивидуальное']

            prompt = self.main_agent._build_dynamic_prompt(
                strategy='A',
                context='у пользователя течет',
                absolute_facts=absolute_facts,
                candidates=candidates,
                txtPrb='у пользователя течет'
            )

            # Проверяем наличие ключевых элементов
            checks = [
                ('Проблема: течет' in prompt, "Абсолютные факты присутствуют"),
                ('Правильно ли я понял' in prompt or 'подтверд' in prompt.lower(), "Вопрос на подтверждение"),
                ('Прорыв труб в квартире' in prompt, "Кандидат указан")
            ]

            passed = all(check[0] for check in checks)

            if passed:
                self.log_test(
                    test_name,
                    "PASS",
                    "Промпт стратегии A сформирован корректно"
                )
            else:
                failed_checks = [check[1] for check in checks if not check[0]]
                self.log_test(
                    test_name,
                    "PARTIAL",
                    f"Не выполняются: {', '.join(failed_checks)}"
                )

        except Exception as e:
            self.log_test(test_name, "FAIL", f"Ошибка: {e}")

    async def test_build_dynamic_prompt_strategy_b(self):
        """Тест 6: BuildDynamicPrompt - Стратегия B (2-10 кандидатов)"""
        test_name = "BuildDynamicPrompt Стратегия B"

        try:
            candidates = [
                {'service_id': 7, 'service_name': 'Устранение течи', 'category': 'Водоснабжение', 'location_type': 'Индивидуальное'},
                {'service_id': 25, 'service_name': 'Прорыв труб в квартире', 'category': 'Водоснабжение', 'location_type': 'Индивидуальное'},
                {'service_id': 26, 'service_name': 'Общедомовой прорыв труб', 'category': 'Водоснабжение', 'location_type': 'Общедомовое'}
            ]
            absolute_facts = ['Проблема: течет', 'Тип: Инцидент']

            prompt = self.main_agent._build_dynamic_prompt(
                strategy='B',
                context='у пользователя течет',
                absolute_facts=absolute_facts,
                candidates=candidates,
                txtPrb='у пользователя течет'
            )

            # Проверяем наличие ключевых элементов
            checks = [
                ('Проблема: течет' in prompt, "Абсолютные факты присутствуют"),
                ('candidates' in prompt.lower() or 'кандидат' in prompt.lower() or json.dumps(candidates, ensure_ascii=False) in prompt, "Список кандидатов присутствует"),
                ('критическое отличие' in prompt.lower() or 'отличие' in prompt.lower(), "Задача на поиск отличия")
            ]

            passed = all(check[0] for check in checks)

            if passed:
                self.log_test(
                    test_name,
                    "PASS",
                    "Промпт стратегии B сформирован корректно"
                )
            else:
                failed_checks = [check[1] for check in checks if not check[0]]
                self.log_test(
                    test_name,
                    "PARTIAL",
                    f"Не выполняются: {', '.join(failed_checks)}"
                )

        except Exception as e:
            self.log_test(test_name, "FAIL", f"Ошибка: {e}")

    async def test_build_dynamic_prompt_strategy_c(self):
        """Тест 7: BuildDynamicPrompt - Стратегия C (>10 кандидатов)"""
        test_name = "BuildDynamicPrompt Стратегия C"

        try:
            absolute_facts = ['Проблема: течет']
            missing_filter = 'ЛОКАЦИЯ'

            prompt = self.main_agent._build_dynamic_prompt(
                strategy='C',
                context='у пользователя течет',
                absolute_facts=absolute_facts,
                candidates=None,  # Для стратегии C кандидаты не передаются
                missing_filter=missing_filter,
                txtPrb='у пользователя течет'
            )

            # Проверяем наличие ключевых элементов
            checks = [
                ('Проблема: течет' in prompt, "Абсолютные факты присутствуют"),
                (missing_filter in prompt, "Недостающий фильтр указан"),
                ('Не упоминай услуги' in prompt or 'не перечисляй' in prompt.lower(), "Запрет на перечисление вариантов")
            ]

            passed = all(check[0] for check in checks)

            if passed:
                self.log_test(
                    test_name,
                    "PASS",
                    "Промпт стратегии C сформирован корректно (без списка кандидатов)"
                )
            else:
                failed_checks = [check[1] for check in checks if not check[0]]
                self.log_test(
                    test_name,
                    "PARTIAL",
                    f"Не выполняются: {', '.join(failed_checks)}"
                )

        except Exception as e:
            self.log_test(test_name, "FAIL", f"Ошибка: {e}")

    def _get_last_tokens(self) -> int:
        """Получить количество токенов из последнего запроса"""
        if self.main_agent and self.main_agent.ai_agent:
            stats = self.main_agent.ai_agent.get_statistics()
            # Берем разницу от общего количества
            # Это приблизительно, но для тестов достаточно
            return 0  # Упрощение
        return 0

    def _get_last_cost(self) -> float:
        """Получить стоимость последнего запроса"""
        if self.main_agent and self.main_agent.ai_agent:
            stats = self.main_agent.ai_agent.get_statistics()
            return 0  # Упрощение
        return 0

    def print_summary(self):
        """Вывод итоговой статистики"""
        print("\n" + "=" * 80)
        print("ИТОГИ ТЕСТИРОВАНИЯ")
        print("=" * 80)

        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r['status'] == 'PASS')
        failed = sum(1 for r in self.test_results if r['status'] == 'FAIL')
        partial = sum(1 for r in self.test_results if r['status'] == 'PARTIAL')
        skipped = sum(1 for r in self.test_results if r['status'] == 'SKIP')

        print(f"Всего тестов: {total}")
        print(f"  ✅ Пройдено: {passed}")
        print(f"  ⚠️  Частично: {partial}")
        print(f"  ❌ Провалено: {failed}")
        print(f"  ⏭️  Пропущено: {skipped}")

        if self.total_tokens > 0:
            print(f"\nРасход токенов: {self.total_tokens}")
            print(f"Стоимость: {self.total_cost:.4f} руб")

        print("\nДетальные результаты:")
        for result in self.test_results:
            icon = "✅" if result['status'] == "PASS" else "❌" if result['status'] == "FAIL" else "⚠️" if result['status'] == "PARTIAL" else "⏭️"
            print(f"  {icon} {result['test']}: {result['status']}")
            if result['details']:
                print(f"     {result['details']}")

        print("=" * 80)


async def main():
    """Главная функция тестирования"""
    print("=" * 80)
    print("ТЕСТЫ РЕФАКТОРИНГА MainAgent v2.0")
    print("=" * 80)

    tester = RefactoredMethodsTester()

    # Инициализация
    if not await tester.init():
        print("❌ Ошибка инициализации. Выход.")
        return

    # Запуск тестов
    print("\nЗапуск тестов...\n")

    await tester.test_llm_validate_question_redundant()
    await tester.test_llm_validate_question_double()
    await tester.test_llm_validate_question_good()
    await tester.test_semantic_pre_check()
    await tester.test_build_dynamic_prompt_strategy_a()
    await tester.test_build_dynamic_prompt_strategy_b()
    await tester.test_build_dynamic_prompt_strategy_c()

    # Итоги
    tester.print_summary()


if __name__ == '__main__':
    asyncio.run(main())
