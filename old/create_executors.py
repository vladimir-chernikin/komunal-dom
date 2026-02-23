#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Создание исполнителей и сотрудников УК
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from django.contrib.auth.models import User
from portal.models import UserProfile

# Исполнители
executors = [
    {
        'username': 'plumber1',
        'password': 'Plumber1_2026',
        'first_name': 'Иван',
        'last_name': 'Сантехников',
        'role': 'executor',
        'specialization': 'plumber',
        'responsibilities': 'Выполнение заявок по водоснабжению и канализации. Устранение засоров, замена труб, установка сантехники.'
    },
    {
        'username': 'plumber2',
        'password': 'Plumber2_2026',
        'first_name': 'Петр',
        'last_name': 'Водников',
        'role': 'executor',
        'specialization': 'plumber',
        'responsibilities': 'Выполнение заявок по водоснабжению и канализации. Устранение засоров, замена труб, установка сантехники.'
    },
    {
        'username': 'electrician1',
        'password': 'Electro1_2026',
        'first_name': 'Сергей',
        'last_name': 'Электриков',
        'role': 'executor',
        'specialization': 'electrician',
        'responsibilities': 'Выполнение заявок по электричеству. Замена проводки, розеток, выключателей, ремонт освещения.'
    },
    {
        'username': 'electrician2',
        'password': 'Electro2_2026',
        'first_name': 'Александр',
        'last_name': 'Токов',
        'role': 'executor',
        'specialization': 'electrician',
        'responsibilities': 'Выполнение заявок по электричеству. Замена проводки, розеток, выключателей, ремонт освещения.'
    },
    {
        'username': 'worker1',
        'password': 'Worker1_2026',
        'first_name': 'Николай',
        'last_name': 'Работников',
        'role': 'executor',
        'specialization': 'general_worker',
        'responsibilities': 'Выполнение общих работ. Уборка территории, погрузка-разгрузка, помощь другим специалистам.'
    },
    {
        'username': 'worker2',
        'password': 'Worker2_2026',
        'first_name': 'Дмитрий',
        'last_name': 'Помощников',
        'role': 'executor',
        'specialization': 'general_worker',
        'responsibilities': 'Выполнение общих работ. Уборка территории, погрузка-разгрузка, помощь другим специалистам.'
    },
]

# Сотрудники УК
staff = [
    {
        'username': 'dispatcher1',
        'password': 'Dispatcher1_2026',
        'first_name': 'Елена',
        'last_name': 'Диспетчерова',
        'role': 'uk_user',
        'job_title': 'dispatcher',
        'responsibilities': 'Прием звонков от жителей, создание заявок, распределение заявок между исполнителями, контроль выполнения.'
    },
    {
        'username': 'chief_engineer1',
        'password': 'ChiefEng1_2026',
        'first_name': 'Виктор',
        'last_name': 'Инженеров',
        'role': 'uk_user',
        'job_title': 'chief_engineer',
        'responsibilities': 'Координация технической службы, контроль качества работ, согласование сложных заявок, руководство исполнителями.'
    },
]

def create_user(data):
    """Создание пользователя"""
    try:
        # Проверяем существует ли пользователь
        if User.objects.filter(username=data['username']).exists():
            print(f"❌ Пользователь {data['username']} УЖЕ существует")
            return False

        # Создаем пользователя
        user = User.objects.create_user(
            username=data['username'],
            password=data['password'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            is_staff=True,  # Доступ к админке
            is_active=True,
        )

        # Создаем профиль
        profile = UserProfile.objects.create(
            user=user,
            role=data['role'],
            specialization=data.get('specialization'),
            job_title=data.get('job_title'),
            responsibilities=data.get('responsibilities'),
            timezone='Europe/Moscow',  # Часовой пояс по умолчанию
        )

        print(f"✅ Создан: {data['username']} ({data['first_name']} {data['last_name']})")
        return True

    except Exception as e:
        print(f"❌ Ошибка при создании {data['username']}: {e}")
        return False

def main():
    print("=" * 60)
    print("Создание исполнителей и сотрудников УК")
    print("=" * 60)

    print("\n--- Исполнители ---")
    executor_count = 0
    for executor_data in executors:
        if create_user(executor_data):
            executor_count += 1

    print(f"\nСоздано исполнителей: {executor_count} из {len(executors)}")

    print("\n--- Сотрудники УК ---")
    staff_count = 0
    for staff_data in staff:
        if create_user(staff_data):
            staff_count += 1

    print(f"\nСоздано сотрудников: {staff_count} из {len(staff)}")

    print("\n" + "=" * 60)
    print(f"ИТОГО: {executor_count + staff_count} из {len(executors) + len(staff)}")
    print("=" * 60)

if __name__ == '__main__':
    main()
