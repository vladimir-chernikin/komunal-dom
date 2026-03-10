#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Удаление и пересоздание исполнителей с профилями
"""

import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
django.setup()

from django.contrib.auth.models import User
from portal.models import UserProfile

# Список пользователей для удаления и пересоздания
users_to_recreate = [
    'plumber1', 'plumber2',
    'electrician1', 'electrician2',
    'worker1', 'worker2',
    'dispatcher1', 'chief_engineer1',
]

def delete_and_recreate():
    """Удаление и пересоздание пользователей"""
    for username in users_to_recreate:
        try:
            # Удаляем пользователя (каскадно удалится профиль)
            user = User.objects.get(username=username)
            user.delete()
            print(f"✅ Удален: {username}")
        except User.DoesNotExist:
            print(f"⚠️  Не найден: {username}")

if __name__ == '__main__':
    print("Удаление пользователей без профилей...")
    delete_and_recreate()
    print("\nТеперь запустите create_executors.py")
