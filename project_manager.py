#!/usr/bin/env python3
import subprocess
import time
import json
from datetime import datetime

class ProjectManager:
    def __init__(self):
        self.services = {
            'bot': 'address-bot',
            'monitor': 'bot-monitor',
            'web': 'gunicorn-komunal-dom'
        }

    def get_status(self):
        """Получает статус всех сервисов"""
        status = {}
        for service_name, service in self.services.items():
            try:
                result = subprocess.run(
                    ["systemctl", "is-active", service],
                    capture_output=True,
                    text=True
                )
                status[service_name] = {
                    'active': result.stdout.strip() == 'active',
                    'status': result.stdout.strip()
                }
            except Exception as e:
                status[service_name] = {
                    'active': False,
                    'status': f'error: {e}'
                }
        return status

    def start_all(self):
        """Запускает все сервисы"""
        for service_name, service in self.services.items():
            print(f"Запуск {service_name}...")
            subprocess.run(["systemctl", "start", service], check=False)
            time.sleep(2)

    def stop_all(self):
        """Останавливает все сервисы"""
        for service_name, service in self.services.items():
            print(f"Остановка {service_name}...")
            subprocess.run(["systemctl", "stop", service], check=False)
            time.sleep(2)

    def restart_service(self, service_name):
        """Перезапускает конкретный сервис"""
        if service_name in self.services:
            service = self.services[service_name]
            print(f"Перезапуск {service_name} ({service})...")
            subprocess.run(["systemctl", "restart", service], check=True)
            return True
        return False

    def show_logs(self, service_name, lines=50):
        """Показывает логи сервиса"""
        if service_name in self.services:
            service = self.services[service_name]
            subprocess.run(["journalctl", "-u", service, "-n", str.lines), "-f"])

    def show_status_dashboard(self):
        """Показывает дашборд статуса"""
        while True:
            print("\n" + "="*60)
            print(f"СТАТУС ПРОЕКТА komunal-dom.ru - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60)

            status = self.get_status()
            for service_name, info in status.items():
                status_icon = "✅" if info['active'] else "❌"
                print(f"{status_icon} {service_name.upper():15} - {info['status']}")

            print("\nДействия:")
            print("1. Перезапустить все")
            print("2. Показать логи бота")
            print("3. Показать логи веб-сервера")
            print("4. Выход")

            try:
                choice = input("\nВыберите действие (1-4): ").strip()
                if choice == "1":
                    self.stop_all()
                    time.sleep(3)
                    self.start_all()
                elif choice == "2":
                    self.show_logs('bot')
                elif choice == "3":
                    self.show_logs('web')
                elif choice == "4":
                    break
                else:
                    print("Неверный выбор")

            except KeyboardInterrupt:
                break

            time.sleep(5)

if __name__ == "__main__":
    manager = ProjectManager()

    if len(__import__('sys').argv) > 1:
        command = __import__('sys').argv[1]
        if command == "status":
            print(json.dumps(manager.get_status(), indent=2, ensure_ascii=False))
        elif command == "start":
            manager.start_all()
        elif command == "stop":
            manager.stop_all()
        elif command == "dashboard":
            manager.show_status_dashboard()
    else:
        manager.show_status_dashboard()