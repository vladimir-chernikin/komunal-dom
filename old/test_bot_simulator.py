#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TestBotSimulator - тестовый бот-имитатор пользователя с AI

Имитирует реального пользователя, у которого есть проблема.
Использует AIAgentService для генерации ответов боту-диспетчеру.

Особенности:
- Генерирует случайное имя при запуске
- Имеет память диалога
- Выдает информацию поэтапно (имитирует реальное поведение)
- Использует AI для генерации ответов
"""

import asyncio
import logging
import random
from typing import List, Dict, Optional
from decouple import config
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TestBotSimulator:
    """Тестовый бот-имитатор пользователя"""

    # Список имен для генерации
    NAMES = [
        'Александр', 'Михаил', 'Дмитрий', 'Сергей', 'Андрей',
        'Алексей', 'Максим', 'Владимир', 'Константин', 'Игорь',
        'Елена', 'Ольга', 'Наталья', 'Татьяна', 'Анна',
        'Мария', 'Екатерина', 'Светлана', 'Ирина', 'Юлия'
    ]

    # Сценарии проблем для тестирования
    SCENARIOS = {
        'proryv_trub': {
            'description': 'Прорыв труб в квартире',
            'initial_message': 'привет',
            'steps': [
                {
                    'situation': 'После приветствия ботом',
                    'information': 'у меня прорвало трубу',
                    'context': 'Пользователь сообщает о проблеме'
                },
                {
                    'situation': 'Когда бот спрашивает где именно',
                    'information': 'в квартире',
                    'context': 'Пользователь уточняет локацию'
                }
            ]
        },
        'tecy_v_k_vanne': {
            'description': 'У пользователя течь в ванной',
            'initial_message': 'привет',
            'steps': [
                {
                    'situation': 'После приветствия ботом',
                    'information': 'у меня течет',
                    'context': 'Пользователь сообщает о проблеме'
                },
                {
                    'situation': 'Когда бот спрашивает где именно',
                    'information': 'в ванной',
                    'context': 'Пользователь уточняет локацию'
                }
            ]
        },
        'net_sveta': {
            'description': 'Нет света в квартире',
            'initial_message': 'добрый день',
            'steps': [
                {'situation': 'После приветствия', 'information': 'выключилось электричество'},
                {'situation': 'Уточнение локации', 'information': 'в квартире'}
            ]
        },
        'zasor': {
            'description': 'Засор в канализации',
            'initial_message': 'помогите',
            'steps': [
                {'situation': 'После вопроса бота', 'information': 'засор в раковине'},
                {'situation': 'Уточнение', 'information': 'на кухне'}
            ]
        }
    }

    def __init__(self, ai_agent_service=None, message_handler=None):
        """
        Инициализация тестового бота

        Args:
            ai_agent_service: AIAgentService для генерации ответов
            message_handler: MessageHandlerService для обработки сообщений
        """
        self.ai_agent = ai_agent_service
        self.message_handler = message_handler

        # Генерируем персональные данные
        self.name = random.choice(self.NAMES)
        self.user_id = f"test_user_{random.randint(1000, 9999)}"
        self.session_id = f"test_session_{random.randint(10000, 99999)}"

        # История диалога
        self.dialog_history: List[Dict] = []

        # Текущий сценарий
        self.current_scenario = None
        self.current_step = 0

        logger.info(f"TestBotSimulator инициализирован: {self.name} (ID: {self.user_id})")

    def set_scenario(self, scenario_key: str):
        """
        Установить сценарий тестирования

        Args:
            scenario_key: Ключ сценария из SCENARIOS
        """
        if scenario_key not in self.SCENARIOS:
            raise ValueError(f"Неизвестный сценарий: {scenario_key}")

        self.current_scenario = self.SCENARIOS[scenario_key]
        self.current_step = 0

        logger.info(f"Установлен сценарий: {self.current_scenario['description']}")

    async def generate_response(self, bot_message: str, situation_context: str = "") -> str:
        """
        Генерация ответа по сценарию

        Args:
            bot_message: Последнее сообщение от бота-диспетчера
            situation_context: Описание текущей ситуации

        Returns:
            str: Ответ по сценарию
        """
        # Используем сценарий напрямую вместо AI для предсказуемого тестирования
        return self._scenario_based_response(bot_message)

    def _create_simulator_prompt(self, bot_message: str, situation_context: str) -> str:
        """Создать промпт для генерации ответа имитатора"""

        # Формируем историю диалога
        history_text = ""
        if self.dialog_history:
            for msg in self.dialog_history[-5:]:
                role = "Бот-диспетчер" if msg['role'] == 'bot' else f"{self.name} (пользователь)"
                history_text += f"{role}: {msg['text']}\n"

        prompt = f"""Ты - {self.name}, обычный человек, который обратился в диспетчерскую управляющей компании по поводу проблемы.

ИНФОРМАЦИЯ О ТЕБЕ:
- Имя: {self.name}
- Ситуация: {situation_context}

ИСТОРИЯ ДИАЛОГА:
{history_text}

ПОСЛЕДНЕЕ СООБЩЕНИЕ ОТ БОТА-ДИСПЕТЧЕРА:
"{bot_message}"

ЗАДАЧА:
Ответь на сообщение бота-диспетчера от лица {self.name}. Правила:
1. Ответ должен быть кратким (1-2 предложения)
2. НЕ используй эмодзи
3. Выдавай информацию постепенно, поэтапно (как реальные люди)
4. Если бот задает вопрос - ответь на него
5. Если бот просит уточнить детали - дай следующую порцию информации
6. Используй простые разговорные фразы
7. Твой ответ должен быть максимально естественным

Верни только твой ответ, без объяснений и кавычек.

Ответ {self.name}:"""

        return prompt

    def _scenario_based_response(self, bot_message: str) -> str:
        """Генерация ответа по сценарию (без AI)"""
        if not self.current_scenario:
            return "Помогите"

        bot_lower = bot_message.lower()
        steps = self.current_scenario['steps']

        # Если еще остались шаги сценария
        if self.current_step < len(steps):
            response = steps[self.current_step]['information']
            # Переходим к следующему шагу для следующего раза
            self.current_step += 1
            logger.info(f"TestBot: Ответ по сценарию (шаг {self.current_step}): '{response}'")
            return response
        else:
            # Сценарий завершен, повторяем последний ответ
            logger.warning(f"TestBot: Сценарий завершен, повторяем последний шаг")
            return steps[-1]['information']

    def _fallback_response(self, bot_message: str, situation_context: str) -> str:
        """Fallback ответ без AI (устарел, используйте _scenario_based_response)"""
        return self._scenario_based_response(bot_message)

    async def run_test_scenario(
        self,
        scenario_key: str,
        max_turns: int = 10
    ) -> Dict:
        """
        Запуск тестового сценария

        Args:
            scenario_key: Ключ сценария
            max_turns: Максимальное количество ходов диалога

        Returns:
            Dict: Результат тестирования
        """
        logger.info(f"=" * 60)
        logger.info(f"НАЧИНАЕМ ТЕСТИРОВАНИЕ: {scenario_key}")
        logger.info(f"Сценарий: {self.SCENARIOS[scenario_key]['description']}")
        logger.info(f"Имитатор: {self.name}")
        logger.info(f"=" * 60)

        # Устанавливаем сценарий
        self.set_scenario(scenario_key)

        # Инициализируем первым сообщением
        initial_msg = self.current_scenario['initial_message']
        self.dialog_history.append({'role': 'user', 'text': initial_msg})

        print(f"\n{self.name}: {initial_msg}\n")

        turn = 0
        while turn < max_turns:
            turn += 1
            logger.info(f"\n--- Ход {turn} ---")

            # Получаем последнее сообщение пользователя
            user_message = self.dialog_history[-1]['text']

            # Отправляем в MessageHandler
            try:
                result = await self.message_handler.handle_incoming_message(
                    text=user_message,
                    user_id=self.user_id,
                    channel='test_bot',
                    session_id=self.session_id
                )

                bot_response = result.get('response', '')
                status = result.get('status')
                service_detected = result.get('service_detected')

                logger.info(f"Bot status: {status}, service: {service_detected}")

            except Exception as e:
                logger.error(f"Ошибка обработки: {e}")
                bot_response = "Произошла ошибка. Попробуйте позже."
                status = 'error'
                service_detected = None

            print(f"Диспетчер: {bot_response}\n")

            # Добавляем ответ бота в историю
            self.dialog_history.append({'role': 'bot', 'text': bot_response})

            # Проверяем, успешно ли определена услуга
            if status == 'SUCCESS' and service_detected:
                logger.info("=" * 60)
                logger.info(f"✅ УСПЕХ: Услуга определена (ID: {service_detected})")
                logger.info(f"=" * 60)
                return {
                    'status': 'success',
                    'service_id': service_detected,
                    'turns': turn,
                    'dialog_history': self.dialog_history
                }

            # Генерируем следующий ответ пользователя по сценарию
            user_response = await self.generate_response(bot_response)

            print(f"{self.name}: {user_response}\n")

            # Добавляем ответ пользователя в историю
            self.dialog_history.append({'role': 'user', 'text': user_response})

            # Небольшая пауза между сообщениями
            await asyncio.sleep(1)

        # Превышен лимит ходов
        logger.warning("=" * 60)
        logger.warning(f"⚠️ Лимит ходов exceeded ({max_turns})")
        logger.warning(f"=" * 60)
        return {
            'status': 'timeout',
            'turns': turn,
            'dialog_history': self.dialog_history
        }


async def main():
    """Главная функция для запуска тестов"""

    # Импортируем сервисы
    from main_agent import MainAgent
    from ai_agent_service import AIAgentService
    from message_handler_service import MessageHandlerService

    logger.info("Инициализация сервисов...")

    # Инициализируем сервисы
    try:
        ai_agent = AIAgentService()
        main_agent = MainAgent()
        message_handler = MessageHandlerService(main_agent=main_agent)
    except Exception as e:
        logger.error(f"Ошибка инициализации сервисов: {e}")
        logger.error("Убедитесь что:")
        logger.error("1. Django настроен правильно")
        logger.error("2. База данных доступна")
        logger.error("3. YandexGPT API ключи настроены")
        return

    # Создаем тестового бота
    simulator = TestBotSimulator(
        ai_agent_service=ai_agent,
        message_handler=message_handler
    )

    # Запускаем тесты
    scenarios = ['proryv_trub']  # Можно добавить больше сценариев

    for scenario_key in scenarios:
        print("\n" + "=" * 80)
        print(f"ЗАПУК ТЕСТА: {scenario_key}")
        print("=" * 80 + "\n")

        result = await simulator.run_test_scenario(scenario_key, max_turns=10)

        print("\n" + "=" * 80)
        print(f"РЕЗУЛЬТАТ ТЕСТА: {scenario_key}")
        print("=" * 80)
        print(f"Статус: {result['status']}")
        print(f"Ходов: {result['turns']}")
        if result.get('service_id'):
            print(f"Определенная услуга: {result['service_id']}")

        # Создаем нового симулятора для следующего теста
        simulator = TestBotSimulator(
            ai_agent_service=ai_agent,
            message_handler=message_handler
        )

    print("\n" + "=" * 80)
    print("ВСЕ ТЕСТЫ ЗАВЕРШЕНЫ")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    # Настраиваем Django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')

    import django
    django.setup()

    # Запускаем асинхронный тест
    asyncio.run(main())
