#!/usr/bin/env python3
import telebot
import subprocess
import json
from datetime import datetime

# Токен для управляющего бота (нужен отдельный токен)
CONTROL_BOT_TOKEN = "ВАШ_УПРАВЛЯЮЩИЙ_БОТ_ТОКЕН"  # Замените на реальный токен
ADMIN_USER_ID = None  # Ваш Telegram ID для доступа

bot = telebot.TeleBot(CONTROL_BOT_TOKEN)

class SystemController:
    def __init__(self):
        self.services = {
            'bot': 'address-bot',
            'monitor': 'bot-monitor',
            'web': 'gunicorn-komunal-dom'
        }

    def get_status(self):
        """Получает статус всех сервисов"""
        status = {}
        for name, service in self.services.items():
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True,
                    text=True
                )
                status[name] = result.stdout.strip()
            except:
                status[name] = "error"
        return status

    def restart_service(self, service_name):
        """Перезапускает сервис"""
        if service_name in self.services:
            service = self.services[service_name]
            try:
                subprocess.run(["systemctl", "restart", service], check=True)
                return f"✅ {service_name} перезапущен"
            except Exception as e:
                return f"❌ Ошибка перезапуска {service_name}: {e}"
        return "❌ Неизвестный сервис"

    def get_logs(self, service_name, lines=20):
        """Получает последние строки логов"""
        if service_name in self.services:
            service = self.services[service_name]
            try:
                result = subprocess.run(
                    ["journalctl", "-u", service, "-n", str(lines)],
                    capture_output=True,
                    text=True
                )
                return result.stdout[-2000:]  # Ограничиваем размер
            except Exception as e:
                return f"Ошибка получения логов: {e}"
        return "Неизвестный сервис"

controller = SystemController()

@bot.message_handler(commands=['start'])
def start_message(message):
    if ADMIN_USER_ID and message.from_user.id != ADMIN_USER_ID:
        bot.reply_to(message, "❌ Доступ запрещен")
        return

    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.add(telebot.types.InlineKeyboardButton("📊 Статус", callback_data="status"))
    keyboard.add(telebot.types.InlineKeyboardButton("🔄 Перезапустить бота", callback_data="restart_bot"))
    keyboard.add(telebot.types.InlineKeyboardButton("📝 Логи бота", callback_data="logs_bot"))
    keyboard.add(telebot.types.InlineKeyboardButton("🌐 Перезапустить сайт", callback_data="restart_web"))

    bot.send_message(message.chat.id,
        "🤖 Управление проектом komunal-dom.ru\n\n"
        "Выберите действие:",
        reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if ADMIN_USER_ID and call.from_user.id != ADMIN_USER_ID:
        bot.answer_callback_query(call.id, "❌ Доступ запрещен")
        return

    try:
        if call.data == "status":
            status = controller.get_status()
            message = "📊 **Статус сервисов:**\n\n"
            for name, stat in status.items():
                icon = "✅" if stat == "active" else "❌"
                message += f"{icon} **{name.upper()}**: {stat}\n"

            bot.send_message(call.message.chat.id, message, parse_mode="Markdown")

        elif call.data == "restart_bot":
            result = controller.restart_service('bot')
            bot.send_message(call.message.chat.id, result)

        elif call.data == "restart_web":
            result = controller.restart_service('web')
            bot.send_message(call.message.chat.id, result)

        elif call.data == "logs_bot":
            logs = controller.get_logs('bot')
            if len(logs) > 4000:
                logs = logs[-4000:] + "..."
            bot.send_message(call.message.chat.id, f"📝 **Логи бота:**\n\n```\n{logs}\n```", parse_mode="Markdown")

    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ Ошибка: {e}")

    bot.answer_callback_query(call.id)

if __name__ == "__main__":
    print("Управляющий бот запущен...")
    bot.polling()