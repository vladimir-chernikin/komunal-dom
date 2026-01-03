#!/usr/bin/env python3
"""
Скрипт для переименования .docx файлов в полные названия документов
Извлекает полное название с первой страницы и переименовывает файлы
"""

import os
import re
import sys
from pathlib import Path
from docx import Document

def extract_full_name(doc_path: str) -> str:
    """
    Извлекает полное название документа с первой страницы

    Args:
        doc_path: Путь к .docx файлу

    Returns:
        Полное название документа
    """
    try:
        doc = Document(doc_path)

        # Читаем первые параграфы
        full_name_parts = []
        found_date = False
        found_number = False

        for para in doc.paragraphs[:30]:  # Первые 30 параграфов
            text = para.text.strip()

            if not text:
                continue

            # Проверяем на тип документа (заголовки капсом)
            if text.isupper() and len(text) < 100:
                # Пропускаем общие заголовки
                if any(skip in text for skip in [
                    'МИНИСТЕРСТВО', 'ПРАВИТЕЛЬСТВО', 'РОССИЙСКОЙ ФЕДЕРАЦИИ',
                    'ФЕДЕРАЛЬНЫЙ ЗАКОН', 'ГОСУДАРСТВЕННАЯ ДУМА', 'СОВЕТА ФЕДЕРАЦИИ'
                ]):
                    continue

                # Это часть названия документа
                full_name_parts.append(text)
                continue

            # Проверяем на дату и номер
            if text.startswith('от ') and 'г.' in text:
                found_date = True
                # Форматируем дату
                date_part = text.replace('от ', '').replace(' г.', '')
                full_name_parts.append(date_part)
                continue

            # Проверяем на номер
            if re.match(r'^[N№]\s*\d+', text):
                found_number = True
                full_name_parts.append(text)
                continue

            # Если нашли дату и номер - выходим
            if found_date and found_number:
                break

            # Ограничиваем количество частей названия
            if len(full_name_parts) >= 5:
                break

        if full_name_parts:
            # Собираем название
            full_name = ' '.join(full_name_parts)

            # Очищаем от лишних пробелов и символов
            full_name = ' '.join(full_name.split())

            # Заменяем недопустимые символы для имени файла
            invalid_chars = '<>:"/\\|?*'
            for char in invalid_chars:
                full_name = full_name.replace(char, '-')

            return full_name
        else:
            return None

    except Exception as e:
        print(f"Ошибка при чтении {doc_path}: {e}")
        return None


def rename_documents(directory: str, dry_run: bool = True):
    """
    Переименовывает документы в полные названия

    Args:
        directory: Директория с документами
        dry_run: Если True, только показывает что будет переименовано
    """
    dir_path = Path(directory)

    if not dir_path.exists():
        print(f"❌ Директория не найдена: {directory}")
        return

    # Находим все .docx файлы
    docx_files = sorted(dir_path.glob("orig_*.docx"))

    if not docx_files:
        print(f"❌ В директории {directory} нет .docx файлов с префиксом orig_")
        return

    print("=" * 80)
    print(f"НАЙДЕНО ФАЙЛОВ: {len(docx_files)}")
    print("=" * 80)

    rename_map = {}

    for i, docx_file in enumerate(docx_files, 1):
        print(f"\n[{i}/{len(docx_files)}] Обработка: {docx_file.name}")
        print("-" * 80)

        # Извлекаем полное название
        full_name = extract_full_name(str(docx_file))

        if full_name:
            new_name = f"orig_{full_name}.docx"

            print(f"Старое название: {docx_file.name}")
            print(f"Новое название: {new_name}")

            # Проверяем длину имени файла
            if len(new_name) > 255:
                print(f"⚠️  Предупреждение: новое название слишком длинное ({len(new_name)} символов)")
                # Обрезаем если нужно
                new_name = new_name[:250] + ".docx"
                print(f"Обрезанное название: {new_name}")

            rename_map[str(docx_file)] = str(dir_path / new_name)
        else:
            print(f"❌ Не удалось извлечь название из файла")
            print(f"   Файл останется: {docx_file.name}")

    # Применяем переименование
    if rename_map:
        print("\n" + "=" * 80)
        if dry_run:
            print("РЕЖИМ ПРЕДПРОСМОТРА - файлы НЕ будут переименованы")
            print("=" * 80)
            print("\nДля выполнения переименования запустите с параметром --execute")
        else:
            print("ВЫПОЛНЕНИЕ ПЕРЕИМЕНОВАНИЯ...")
            print("=" * 80)

            # Переименовываем файлы
            for old_path, new_path in rename_map.items():
                try:
                    # Проверяем существует ли уже файл с таким именем
                    if os.path.exists(new_path):
                        print(f"\n⚠️  Файл уже существует: {Path(new_path).name}")
                        print(f"   Пропускаем: {Path(old_path).name}")
                    else:
                        os.rename(old_path, new_path)
                        print(f"✓ Переименовано: {Path(old_path).name} → {Path(new_path).name}")
                except Exception as e:
                    print(f"❌ Ошибка при переименовании {Path(old_path).name}: {e}")

            print("\n" + "=" * 80)
            print(f"ГОТОВО! Обработано {len(rename_map)} файлов")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Переименование .docx файлов в полные названия документов')
    parser.add_argument('directory', nargs='?', default='/home/olga/normativ_docs/Волков/fulldocx',
                       help='Директория с документами')
    parser.add_argument('--execute', action='store_true',
                       help='Выполнить переименование (без этого флага только просмотр)')

    args = parser.parse_args()

    dry_run = not args.execute

    rename_documents(args.directory, dry_run=dry_run)
