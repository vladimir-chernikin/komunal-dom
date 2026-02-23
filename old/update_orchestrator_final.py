#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, '/var/www/komunal-dom_ru')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')

import django
django.setup()

from llm_tester.models import PromptTemplate

prompt = PromptTemplate.objects.filter(slug='mainagent-orchestrator').first()

if prompt:
    old = prompt.template
    
    # Проверяем что есть в промпте
    print("=== ПРОВЕРКА ПРОМПТА ===")
    print(f"Длина: {len(old)}")
    print(f"Содержит 'КРИТИЧЕСКИЕ': {'КРИТИЧЕСКИЕ' in old}")
    print(f"Содержит 'нет вод': {'нет вод' in old}")
    print(f"Первые 300 символов:")
    print(old[:300])
    
