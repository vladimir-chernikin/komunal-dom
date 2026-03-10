#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import logging

# Добавляем текущую директорию в path для импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from dialog_memory_manager import DialogMemoryManager


def run_tests():
    """Запустить все тесты для DialogMemoryManager"""

    print("\n" + "="*60)
    print("🧪 НАЧИНАЕМ ТЕСТЫ ФАЗЫ 1: DialogMemoryManager")
    print("="*60 + "\n")

    # Тест 1: Извлечение имени
    print("📝 Тест 1: Извлечение имени пользователя")
    memory = DialogMemoryManager("test_dialog", 123)

    # Разные форматы имени
    assert memory.extract_user_name("Я Владимир") == "Владимир", "Ошибка: 'Я Владимир'"
    assert memory.extract_user_name("меня зовут Елена") == "Елена", "Ошибка: 'меня зовут Елена'"
    assert memory.extract_user_name("Это Иван") == "Иван", "Ошибка: 'Это Иван'"
    assert memory.extract_user_name("зовут Петров") == "Петров", "Ошибка: 'зовут Петров'"

    print("✅ Тест 1 пройден: извлечение имени работает корректно")
    print(f"   Имя пользователя: {memory.user_name}\n")

    # Тест 2: Накопление адреса - КЛЮЧЕВОЙ ТЕСТ!
    print("📍 Тест 2: Накопление адреса из кусков")
    memory = DialogMemoryManager("address_test", 456)

    # Сообщение 1: только улица
    result1 = memory.accumulate_address_fragments({'street': 'Ленина'})
    assert result1['street'] == 'Ленина', "Улица не сохранена"
    assert result1['house_number'] is None, "Дом должен быть None"
    print("   Шаг 1: ул. Ленина ✅")

    # Сообщение 2: только дом
    result2 = memory.accumulate_address_fragments({'house_number': '5'})
    assert result2['street'] == 'Ленина', "Улица потеряна! КРИТИЧЕСКАЯ ОШИБКА"
    assert result2['house_number'] == '5', "Дом не сохранен"
    print("   Шаг 2: ул. Ленина + д. 5 ✅")

    # Сообщение 3: только квартира
    result3 = memory.accumulate_address_fragments({'apartment_number': '12'})
    assert result3['street'] == 'Ленина', "Улица потеряна на шаге 3!"
    assert result3['house_number'] == '5', "Дом потерян на шаге 3!"
    assert result3['apartment_number'] == '12', "Квартира не сохранена"
    print("   Шаг 3: ул. Ленина + д. 5 + кв. 12 ✅")

    # Дополнительный компонент
    result4 = memory.accumulate_address_fragments({'entrance': '2'})
    assert result4['street'] == 'Ленина', "Улица потеряна после подъезда!"
    assert result4['house_number'] == '5', "Дом потерян после подъезда!"
    assert result4['apartment_number'] == '12', "Квартира потеряна после подъезда!"
    assert result4['entrance'] == '2', "Подъезд не сохранен"
    print("   Шаг 4: полный адрес + подъезд ✅")

    print("✅ Тест 2 пройден: накопление адреса работает ИДЕАЛЬНО!\n")

    # Тест 3: История сообщений
    print("💬 Тест 3: История сообщений")
    memory = DialogMemoryManager("history_test", 789)

    memory.add_message('user', "Привет")
    memory.add_message('bot', "Здравствуйте!")
    memory.add_message('user', "Как дела?")
    memory.add_message('bot', "Хорошо, чем могу помочь?")

    assert len(memory.conversation_history) == 4, "Неверное количество сообщений"
    assert memory.conversation_history[0]['role'] == 'user', "Первое сообщение не от пользователя"
    assert memory.conversation_history[1]['role'] == 'bot', "Второе сообщение не от бота"
    assert memory.conversation_history[0]['text'] == "Привет", "Текст первого сообщения неверен"

    print("✅ Тест 3 пройден: история сообщений сохраняется корректно")
    print(f"   Всего сообщений: {len(memory.conversation_history)}\n")

    # Тест 4: Получение контекста
    print("🔍 Тест 4: Получение полного контекста")
    context = memory.get_complete_context()

    assert context['user_id'] == 789, "user_id неверен"
    assert context['history_length'] == 4, "history_length неверен"
    assert 'extracted_entities' in context, "extracted_entities отсутствует"
    assert 'last_messages' in context, "last_messages отсутствует"
    assert context['dialog_duration_minutes'] >= 0, "dialog_duration_minutes отрицательный"

    print("✅ Тест 4 пройден: контекст формируется правильно")
    print(f"   Длительность диалога: {context['dialog_duration_minutes']} минут\n")

    # Тест 5: Проверка полноты адреса
    print("📊 Тест 5: Проверка полноты адреса")

    # Пустой адрес
    empty_memory = DialogMemoryManager("empty_test", 999)
    assert empty_memory.get_address_confidence() == 0.0, "Пустой адрес должен иметь 0 уверенности"
    assert not empty_memory.is_address_complete(), "Пустой адрес не должен быть полным"

    # Только улица
    street_memory = DialogMemoryManager("street_test", 998)
    street_memory.accumulate_address_fragments({'street': 'Мира'})
    assert street_memory.get_address_confidence() == 0.25, "Только улица = 0.25"
    assert not street_memory.is_address_complete(), "Только улица не полный адрес"

    # Улица + дом
    full_memory = DialogMemoryManager("full_test", 997)
    full_memory.accumulate_address_fragments({'street': 'Мира', 'house_number': '10'})
    assert full_memory.get_address_confidence() >= 0.5, "Улица + дом должны быть >= 0.5"
    assert full_memory.is_address_complete(), "Улица + дом = полный адрес"

    print("✅ Тест 5 пройден: проверка полноты адреса работает")
    print(f"   Уверенность полного адреса: {full_memory.get_address_confidence():.2f}\n")

    # Тест 6: Контекст услуги
    print("🔧 Тест 6: Контекст услуги")
    memory = DialogMemoryManager("service_test", 888)

    memory.update_service_context(1, "Протечка крана", 0.92, "Течет кран на кухне")

    assert memory.current_service_context is not None, "Контекст услуги не сохранен"
    assert memory.current_service_context['service_id'] == 1, "service_id неверен"
    assert memory.current_service_context['service_name'] == "Протечка крана", "service_name неверен"
    assert memory.current_service_context['confidence'] == 0.92, "confidence неверен"
    assert len(memory.previous_services) == 0, "previous_services должен быть пустым"

    # Обновляем услугу - старая должна перейти в previous_services
    memory.update_service_context(2, "Нет воды", 0.88)
    assert len(memory.previous_services) == 1, "Старая услуга не сохранена в previous_services"
    assert memory.current_service_context['service_name'] == "Нет воды", "Новая услуга не установлена"

    print("✅ Тест 6 пройден: контекст услуги работает корректно")
    print(f"   Текущая услуга: {memory.current_service_context['service_name']}")
    print(f"   Предыдущих услуг: {len(memory.previous_services)}\n")

    # Тест 7: Резюме диалога
    print("📋 Тест 7: Резюме диалога")
    # Используем новый объект чистого memory для этого теста
    summary_memory = DialogMemoryManager("summary_test", 998)
    summary_memory.extract_user_name("Меня зовут Анна")
    summary_memory.accumulate_address_fragments({'street': 'Советская', 'house_number': '15'})
    summary = summary_memory.get_full_address_string()

    assert "Анна" in summary_memory.user_name, "Имя отсутствует"
    assert "ул. Советская" in summary, "Улица отсутствует в адресе"
    assert "д. 15" in summary, "Дом отсутствует в адресе"

    print("✅ Тест 7 пройден: формирование адреса работает правильно")
    print(f"   Адрес: {summary}\n")

    # Финальная проверка
    print("🎉 ФИНАЛЬНАЯ ПРОВЕРКА")
    final_memory = DialogMemoryManager("final_test", 777)

    # Полный цикл
    final_memory.extract_user_name("Я Дмитрий")
    final_memory.add_message('user', "Привет")
    final_memory.add_message('bot', "Здравствуйте!")
    final_memory.accumulate_address_fragments({'street': 'Ленина'})
    final_memory.update_service_context(3, "Засор раковины", 0.85)

    # Проверяем что всё работает вместе
    context = final_memory.get_complete_context()
    assert context['user_name'] == "Дмитрий", "Имя не сохранено"
    assert context['extracted_entities']['street'] == 'Ленина', "Адрес не сохранен"
    assert context['current_service']['service_name'] == "Засор раковины", "Услуга не сохранена"

    print("✅ ФИНАЛЬНАЯ ПРОВЕРКА ПРОЙДЕНА: все компоненты работают вместе!")

    print("\n" + "="*60)
    print("🎉 ВСЕ ТЕСТЫ ФАЗЫ 1 УСПЕШНО ПРОЙДЕНЫ!")
    print("DialogMemoryManager работает ИДЕАЛЬНО! ✅")
    print("Готов к интеграции с другими компонентами!")
    print("="*60 + "\n")

    return True


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"\n❌ ОШИБКА В ТЕСТАХ: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)