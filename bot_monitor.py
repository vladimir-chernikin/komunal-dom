#!/usr/bin/env python3
import subprocess
import time
import logging
from datetime import datetime
import requests
import json

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/bot_monitor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class BotMonitor:
    def __init__(self):
        self.bot_service = "address-bot"
        self.check_interval = 30  # секунд
        self.webhook_url = None  # Можно добавить URL для уведомлений

    def check_service_status(self):
        """Проверяет статус сервиса бота"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", self.bot_service],
                capture_output=True,
                text=True
            )
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Ошибка проверки статуса сервиса: {e}")
            return "unknown"

    def check_bot_responsive(self):
        """Проверяет, отвечает ли бот на сообщения"""
        # Здесь можно добавить проверку через API или Telegram
        # Пока просто проверяем, что процесс работает
        try:
            result = subprocess.run(
                ["pgrep", "-f", "address_bot.py"],
                capture_output=True,
                text=True
            )
            return bool(result.stdout.strip())
        except Exception as e:
            logger.error(f"Ошибка проверки отзывчивости бота: {e}")
            return False

    def restart_service(self):
        """Перезапускает сервис бота"""
        try:
            logger.warning("Перезапуск сервиса бота...")
            subprocess.run(["systemctl", "restart", self.bot_service], check=True)
            time.sleep(5)  # Даем время на запуск
            return True
        except Exception as e:
            logger.error(f"Ошибка перезапуска сервиса: {e}")
            return False

    def send_notification(self, message):
        """Отправляет уведомление о проблеме"""
        logger.critical(message)
        # Здесь можно добавить отправку в Telegram, email и т.д.

    def monitor_loop(self):
        """Основной цикл мониторинга"""
        logger.info("Запуск мониторинга бота...")

        while True:
            try:
                # Проверка статуса сервиса
                status = self.check_service_status()

                if status != "active":
                    self.send_notification(f"Бот не работает! Статус: {status}")
                    if self.restart_service():
                        logger.info("Бот успешно перезапущен")
                    else:
                        self.send_notification("НЕ УДАЛОСЬ ПЕРЕЗАПУСТИТЬ БОТА!")

                # Проверка отзывчивости
                elif not self.check_bot_responsive():
                    self.send_notification("Бот работает, но не отвечает на сообщения")
                    if self.restart_service():
                        logger.info("Бот перезапущен для восстановления отзывчивости")

                # Проверка логов на ошибки
                self.check_logs_for_errors()

            except Exception as e:
                logger.error(f"Ошибка в цикле мониторинга: {e}")

            time.sleep(self.check_interval)

    def check_logs_for_errors(self):
        """Проверяет логи на наличие ошибок"""
        try:
            # Получаем последние 10 строк логов
            result = subprocess.run(
                ["journalctl", "-u", self.bot_service, "-n", "10"],
                capture_output=True,
                text=True
            )

            errors = []
            for line in result.stdout.split('\n'):
                if 'ERROR' in line or 'Exception' in line or 'CRITICAL' in line:
                    errors.append(line)

            if errors:
                logger.warning(f"Найдены ошибки в логах: {len(errors)}")
                for error in errors[-3:]:  # Последние 3 ошибки
                    logger.warning(f"Ошибка: {error}")

        except Exception as e:
            logger.error(f"Ошибка проверки логов: {e}")

if __name__ == "__main__":
    monitor = BotMonitor()
    monitor.monitor_loop()