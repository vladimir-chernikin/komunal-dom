#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Тестирование промта incident_type на реальных запросах

Запуск:
    python test_incident_type_prompt.py
"""

import os
import django
import asyncio
import json
import re
from datetime import datetime, timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'komunal_dom.settings')
os.environ.setdefault('DJANGO_ALLOW_ASYNC_UNSAFE', 'true')
django.setup()

from django.db import connection
from ai_agent_service import AIAgentService


# Промт для тестирования
INCIDENT_TYPE_PROMPT = '''## Роль
Ты — строгий алгоритмический классификатор типа обращения.
Твоя задача — по тексту обращения определить, является ли оно инцидентом или запросом.
Всегда следуй алгоритму по шагам и верни только один JSON-объект.

## Входные данные
TXT_PRB = "{txtPrb}"

Анализируй ТОЛЬКО смысл текста из переменной TXT_PRB, не используй примеры или строки из самого промпта.

## Алгоритм (цепочка рассуждений)

### Шаг 1. Внутренние сущности
Мысленно определи три внутренних сущности на основе текста:
- OBJ — что является основным объектом или тем, к чему относится проблема (конкретная система, устройство, часть инфраструктуры или ресурс).
- EVENT — какое действие, состояние или изменение описывается (что с этим объектом происходит или что с ним хотят сделать).
- PLACE — где происходит описываемая ситуация (помещение, зона, адрес или иная локация).

Если какая-то из сущностей по смыслу не указана явно, считаей её равной null, но продолжай анализ по смыслу текста.

### Шаг 2. Характер ситуации
По смыслу текста определи, к какой группе ближе основная суть обращения:

1. Нарушение нормальной работы сейчас.
   Ответь себе: описывает ли текст ситуацию, в которой что-то, что обычно должно функционировать, сейчас работает явно хуже нормы, не выполняет свою функцию или создаёт заметный дискомфорт/ограничение в использовании.
   Оцени, нужно ли восстановить привычное состояние вещей, чтобы устранить проблему.

2. Опасность для людей или имущества.
   Ответь себе: следует ли из текста, что при отсутствии своевременных действий возникает реальная или очевидная угроза жизни, здоровью или значительному повреждению имущества.
   Обрати внимание, есть ли указания на то, что ситуация требует быстрого реагирования, а не может быть отложена без последствий.

3. Массовое нарушение услуги.
   Ответь себе: показывает ли текст, что важная услуга или ресурс недоступны для группы людей, большого числа потребителей или целого дома, а не только для одного локального объекта.
   Оцени, нарушены ли базовые условия нормального проживания или пользования инфраструктурой для многих.

4. Планируемые действия.
   Ответь себе: описывает ли текст намерение выполнить работу или услугу в будущем (обслуживание, установка, замена, иное действие), без указания на уже наступившую поломку или отклонение от нормы.
   Важно: акцент на организации или заказе работы, а не на устранении возникшей аварийной ситуации.

5. Получение информации.
   Ответь себе: состоит ли обращение главным образом в том, чтобы получить сведения, разъяснения, документы, реквизиты, графики, контакты или другие данные, без описания неисправности, угрозы или отключения услуги.
   Важно: цель — узнать или уточнить, а не починить или восстановить.

### Шаг 3. Классификация типа обращения
Сопоставь свои ответы из шага 2 и определи доминирующий смысл:

- Если основное содержание обращения заключается в том, что:
  • уже нарушена нормальная работа чего-то существенного для пользователя,
  • либо имеется выраженная опасность для людей или значительного ущерба имуществу,
  • либо важная услуга фактически недоступна сразу для многих пользователей,
  относись к обращению как к инциденту.

- Если основное содержание обращения заключается в том, чтобы:
  • организовать работу, обслуживание или иное действие в будущем без признаков уже наступившей аварийной ситуации,
  • либо получить информацию, разъяснения или документы без признаков неисправности или угрозы,
  относись к обращению как к запросу.

Если часть признаков указывает на инцидент, а часть — на запрос, выбери тот тип, который лучше отражает главную цель заявителя: устранить возникшую проблему/опасность или получить услугу/информацию.

Установи переменную incident_type:
- incident_type = "Инцидент" или
- incident_type = "Запрос"
в соответствии с доминирующим смыслом текста.

### Шаг 4. Оценка уверенности
Оцени confidence (от 0.0 до 1.0) по следующим принципам:

- Значение ближе к 1.0 — когда текст однозначно описывает одну из ситуаций из шага 2, без двусмысленности, и выбор типа обращения очевиден.
- Средние значения — когда из текста в целом понятно, что больше похоже на инцидент или запрос, но формулировки неполные или допускают другое толкование.
- Значения ближе к 0.5 — когда информации мало, формулировки размыты, и выбор типа обращения опирается в основном на общую интерпретацию намерения пользователя.

### Шаг 5. Пояснение рассуждений
Сформируй краткое текстовое пояснение reasoning, в котором последовательно и связно опишешь:
- как ты понял OBJ, EVENT и PLACE (если они есть),
- почему решил, что это скорее нарушение работы/опасность/массовое отключение ИЛИ плановое действие/информационная цель,
- как из этого вывода получился выбранный incident_type и уровень confidence.

## Выход
Верни ТОЛЬКО один JSON-объект без какого-либо дополнительного текста до или после, строго в формате:
{{
  "incident_type": "Инцидент" или "Запрос",
  "confidence": число от 0 до 1,
  "reasoning": "краткое связное объяснение твоей цепочки рассуждений",
  "OBJ": "основной объект из текста или null",
  "EVENT": "основное действие/состояние из текста или null",
  "PLACE": "место из текста или null"
}}'''


def get_real_requests(limit=20):
    """Получить последние реальные запросы пользователей"""
    with connection.cursor() as cursor:
        # Берем запросы за последние 3 дня
        three_days_ago = datetime.now() - timedelta(days=3)

        cursor.execute("""
            SELECT
                dl.message_id,
                dl.dialog_id,
                dl.session_id,
                dl.channel,
                dl.message_content,
                dl.timestamp
            FROM dialog_logs dl
            WHERE dl.timestamp >= %s
                AND dl.direction = 'inbound'
                AND dl.message_content IS NOT NULL
                AND LENGTH(dl.message_content) > 5
            ORDER BY dl.timestamp DESC
            LIMIT %s
        """, [three_days_ago, limit])

        results = cursor.fetchall()

    requests = []
    for msg_id, dialog_id, session_id, channel, text, timestamp in results:
        requests.append({
            'message_id': msg_id,
            'dialog_id': str(dialog_id),
            'session_id': session_id,
            'channel': channel,
            'text': text,
            'created_at': timestamp
        })

    return requests


async def test_prompt():
    """Тестирование промта на реальных запросах"""

    print("=" * 80)
    print("ТЕСТИРОВАНИЕ ПРОМТА INCIDENT_TYPE")
    print("=" * 80)
    print()

    # Получаем реальные запросы
    requests = get_real_requests(limit=15)

    if not requests:
        print("❌ Не найдено реальных запросов для тестирования")
        return

    print(f"✅ Загружено {len(requests)} реальных запросов")
    print()

    # Инициализируем AI сервис
    ai_service = AIAgentService(provider='gigachat', default_model='GigaChat')

    results = []

    for i, req in enumerate(requests, 1):
        print(f"─" * 80)
        print(f"ТЕСТ #{i}")
        print(f"─" * 80)
        print(f"📝 Текст: {req['text']}")
        print(f"📅 Дата: {req['created_at']}")
        print(f"💬 Канал: {req['channel']}")
        print()

        # Формируем промт
        prompt = INCIDENT_TYPE_PROMPT.format(txtPrb=req['text'])

        try:
            # Вызываем LLM
            response, usage = await ai_service.call_llm(
                prompt=prompt,
                provider='gigachat',
                model='GigaChat',
                temperature=0.3,
                max_tokens=800,
                session_id=req['dialog_id'],
                message_id=req['message_id']
            )

            # Пытаемся распарсить JSON
            try:
                # Извлекаем JSON из ответа (на случай если есть дополнительный текст)
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    json_str = json_match.group(0)
                    result = json.loads(json_str)
                else:
                    result = {'raw_response': response}

                results.append({
                    'request': req,
                    'response': result,
                    'usage': usage
                })

                # Выводим результат
                print(f"📊 Результат:")
                if 'incident_type' in result:
                    print(f"   • incident_type: {result['incident_type']}")
                    print(f"   • confidence: {result.get('confidence', 'N/A')}")
                    print(f"   • OBJ: {result.get('OBJ', 'N/A')}")
                    print(f"   • EVENT: {result.get('EVENT', 'N/A')}")
                    print(f"   • PLACE: {result.get('PLACE', 'N/A')}")
                    print(f"   • reasoning: {result.get('reasoning', 'N/A')[:100]}...")
                else:
                    print(f"   ⚠️  Не удалось распарсить JSON:")
                    print(f"   {response[:200]}")

                print(f"💰 Стоимость: {usage.get('cost', 0):.4f} руб")
                print(f"🔢 Токены: {usage.get('total_tokens', 0)}")

            except json.JSONDecodeError as e:
                print(f"❌ Ошибка парсинга JSON: {e}")
                print(f"📄 Сырой ответ:")
                print(response[:500])
                results.append({
                    'request': req,
                    'response': {'error': str(e), 'raw': response},
                    'usage': usage
                })

        except Exception as e:
            print(f"❌ Ошибка вызова LLM: {e}")
            results.append({
                'request': req,
                'response': {'error': str(e)},
                'usage': {}
            })

        print()

    # Итоговая статистика
    print("=" * 80)
    print("ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)

    incidents = 0
    requests_count = 0
    errors = 0

    for r in results:
        resp = r['response']
        if 'error' in resp:
            errors += 1
        elif resp.get('incident_type') == 'Инцидент':
            incidents += 1
        elif resp.get('incident_type') == 'Запрос':
            requests_count += 1

    print(f"✅ Всего обработано: {len(results)}")
    print(f"   • Инциденты: {incidents}")
    print(f"   • Запросы: {requests_count}")
    print(f"   • Ошибки: {errors}")

    total_cost = sum(r['usage'].get('cost', 0) for r in results)
    total_tokens = sum(r['usage'].get('total_tokens', 0) for r in results)

    print(f"💰 Общая стоимость: {total_cost:.4f} руб")
    print(f"🔢 Всего токенов: {total_tokens}")


if __name__ == '__main__':
    asyncio.run(test_prompt())
