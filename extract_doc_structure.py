#!/usr/bin/env python3
"""
Экстрактор структуры документов .docx
Создает файлы *_structure.txt для быстрого просмотра содержания документа
"""

import os
import re
from pathlib import Path
from docx import Document
from typing import List, Dict, Any


def extract_structure(doc_path: str) -> str:
    """Извлекает структуру документа"""

    doc = Document(doc_path)
    doc_name = Path(doc_path).stem

    # Определяем тип документа
    doc_type = detect_document_type(doc, doc_name)

    if doc_type == 'code':
        return extract_code_structure(doc, doc_name)
    elif doc_type == 'letter':
        return extract_letter_structure(doc, doc_name)
    else:
        return extract_generic_structure(doc, doc_name)


def detect_document_type(doc: Document, doc_name: str) -> str:
    """Определяет тип документа"""

    doc_text = '\n'.join([p.text for p in doc.paragraphs[:20]])

    # Кодекс (ЖК РФ, ГК РФ и т.д.)
    if any(keyword in doc_name for keyword in ['ЖК РФ', 'ГК', 'Кодекс']):
        return 'code'

    # Федеральный закон - тоже с оглавлением статей
    if any(keyword in doc_name for keyword in ['ФЗ', 'Федеральный закон']):
        return 'code'

    # Письмо или Приказ
    if any(keyword in doc_text.upper() for keyword in ['ПИСЬМО', 'МИНИСТЕРСТВО', 'ПРИКАЗ']):
        return 'letter'

    return 'generic'


def extract_code_structure(doc: Document, doc_name: str) -> str:
    """Извлекает структуру кодекса (разделы, главы, статьи)"""

    lines = []
    lines.append(f"--- Структура для документа: {doc_name}.docx ---")
    lines.append("")

    current_section = None
    current_chapter = None

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue

        # Раздел (РАЗДЕЛ, Раздел)
        if re.match(r'^(РАЗДЕЛ|Раздел)\s+[IVX\d]+', text, re.IGNORECASE):
            current_section = text
            lines.append(text)
            continue

        # Глава (ГЛАВА, Глава)
        if re.match(r'^(ГЛАВА|Глава)\s+\d+', text, re.IGNORECASE):
            current_chapter = text
            lines.append(f"  {text}")
            continue

        # Статья (Статья)
        if re.match(r'^Статья\s+[\d.]+', text, re.IGNORECASE):
            lines.append(f"    {text}")
            continue

    return '\n'.join(lines)


def extract_letter_structure(doc: Document, doc_name: str) -> str:
    """Извлекает структуру письма/приказа с подробными разделами"""

    lines = []
    lines.append(f"--- Структура для документа: {doc_name}.docx ---")
    lines.append("")

    # Анализируем содержимое
    all_text = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            all_text.append(text)

    if not all_text:
        return '\n'.join(lines) + "(Документ пуст или не удалось прочитать)"

    # Извлекаем ключевую информацию
    header_parts = []
    references = []

    for i, text in enumerate(all_text):
        # Заголовок (капсом)
        if text.isupper() and len(text) < 100:
            header_parts.append(text)
            continue

        # Дата и номер
        if re.match(r'^от\s+\d+', text):
            header_parts.append(text)
            continue

        # Ссылки на статьи
        if 'ст.' in text.lower() or 'стать' in text.lower():
            refs = extract_law_references(text)
            references.extend(refs)

        # Постановления
        if 'постановлен' in text.lower() or 'Правил' in text:
            refs = extract_government_resolutions(text)
            references.extend(refs)

    # Формируем структуру с разделами
    if header_parts:
        lines.append("ЗАГОЛОВОЧНАЯ ЧАСТЬ:")
        for part in header_parts[:5]:
            lines.append(f"  - {clean_text(part)}")
        lines.append("")

    # Извлекаем структурированную информацию
    structured_content = extract_structured_content(all_text)

    if references:
        lines.append("НОРМАТИВНЫЕ ССЫЛКИ:")
        for ref in sorted(set(references)):
            lines.append(f"  - {ref}")
        lines.append("")

    # Добавляем структурированный контент
    lines.append(str(structured_content))

    # Подпись
    for text in reversed(all_text):
        if any(keyword in text for keyword in ['Директор', 'Начальник', 'Министр', 'Председатель']):
            lines.append("ПОДПИСЬ:")
            lines.append(f"  - {text}")
            break

    return '\n'.join(lines)


def extract_structured_content(text_list: List[str]) -> 'StructuredContent':
    """Извлекает структурированное содержание по разделам"""

    content = StructuredContent()

    # Сначала ищем ПРЕДМЕТ ДОКУМЕНТА (обычно в начале)
    for i, text in enumerate(text_list[:50]):  # Первые 50 строк
        text_clean = re.sub(r'^\d+\.?\s*', '', text)  # Убираем нумерацию в начале
        text_lower = text_clean.lower()

        # ПРЕДМЕТ ДОКУМЕНТА - ключевые фразы определения
        if any(kw in text_lower for kw in [
            'настоящий порядок определяет', 'настоящие правила определяют',
            'определяет условия, последовательность и сроки',
            'утверждает порядок', 'утвердить порядок',
            'правила предоставления', 'порядок определения',
            'порядок расчета', 'порядок проведения'
        ]):
            sent = clean_text(extract_full_sentence(text_clean))
            if sent and len(sent) > 60 and len(sent) < 500:
                content.add_item('ПРЕДМЕТ ДОКУМЕНТА', sent)
                break  # Нашли предмет - выходим

    # Остальные разделы
    for text in text_list:
        text_clean = re.sub(r'^\d+\.?\s*', '', text)  # Убираем нумерацию в начале

        # Пропускаем строки с перечислениями
        stripped = text_clean.strip()
        if re.match(r'^\s*[а-яА-ЯёЁa-zA-Z\d]?\s*[\)\-\.]', stripped):
            continue
        if stripped.startswith('- ') or stripped.startswith('—'):
            continue

        text_lower = text_clean.lower()

        # ПРОЦЕДУРА - ключевые слова процессов
        if any(kw in text_lower for kw in [
            'заявление и документов', 'осуществляется проверка',
            'рассмотрение заявления', 'принятие решения',
            'вносит изменения', 'представление заявления',
            'направляется заявителю', 'выдача свидетельства'
        ]):
            sent = clean_text(extract_full_sentence(text_clean))
            if sent and len(sent) > 80 and len(sent) < 400:
                # Проверяем что это не перечисление
                if not sent.startswith('(') and not sent.startswith('—'):
                    content.add_item('ПРОЦЕДУРА', sent)

        # СРОКИ - должно содержать числовые значения
        if any(kw in text_lower for kw in [
            'рабочих дней', 'календарных дней', 'месяцев',
            'не позднее', 'не ранее', 'в течение'
        ]):
            sent = clean_text(extract_full_sentence(text_clean))
            if sent and len(sent) > 40 and len(sent) < 300:
                # Проверяем что есть число или единица измерения
                if any(char.isdigit() for char in sent) or 'дней' in sent.lower() or 'месяцев' in sent.lower():
                    content.add_item('СРОКИ', sent)

        # ОСНОВАНИЯ/УСЛОВИЯ - конкретные условия
        if any(kw in text_lower for kw in [
            'основанием для', 'в случае если', 'в случае',
            'при условии что', 'является основанием',
            'условиями являются', 'предусмотренных'
        ]):
            sent = clean_text(extract_full_sentence(text_clean))
            if sent and len(sent) > 60 and len(sent) < 400:
                # Не перечисление
                if not sent.startswith('—') and not sent.startswith('а)'):
                    content.add_item('ОСНОВАНИЯ/УСЛОВИЯ', sent)

        # РЕШЕНИЯ/ПОСЛЕДСТВИЯ - что происходит в результате
        if any(kw in text_lower for kw in [
            'решение о внесении', 'решение об отказе',
            'решение о приостановлении', 'принимает решение',
            'влечет за собой', 'влечет', 'последствием'
        ]):
            sent = clean_text(extract_full_sentence(text_clean))
            if sent and len(sent) > 50 and len(sent) < 400:
                if not sent.startswith('—'):
                    content.add_item('РЕШЕНИЯ/ПОСЛЕДСТВИЯ', sent)

    return content


def extract_full_sentence(text: str) -> str:
    """Извлекает полное предложение до точки"""
    # Разбиваем по точкам
    sentences = text.split('.')
    if sentences:
        first = sentences[0].strip()
        # Если начинается с перечисления - пропускаем
        if re.match(r'^\s*[а-яА-Я]\)\s*', first):
            return ''
        # Добавляем точку если нужно
        if not first.endswith(('.)', ';', ',')):
            first = first + '.'
        return first
    return text


class StructuredContent:
    """Класс для структурирования содержания по разделам"""

    def __init__(self):
        self.sections = {
            'ПРЕДМЕТ ДОКУМЕНТА': [],
            'ПРОЦЕДУРА': [],
            'СРОКИ': [],
            'ОСНОВАНИЯ/УСЛОВИЯ': [],
            'РЕШЕНИЯ/ПОСЛЕДСТВИЯ': []
        }

    def add_item(self, section: str, item: str):
        """Добавляет элемент в раздел"""
        if section in self.sections:
            # Проверяем на дубликаты
            if item not in self.sections[section]:
                # Ограничиваем количество в каждом разделе
                if len(self.sections[section]) < 5:
                    self.sections[section].append(item)

    def __str__(self) -> str:
        """Форматирует структуру в текст"""
        lines = []
        lines.append("ОСНОВНОЕ СОДЕРЖАНИЕ:")
        lines.append("")

        for section, items in self.sections.items():
            if items:
                lines.append(f"  {section}:")
                for item in items:
                    lines.append(f"  - {item}")
                lines.append("")

        return '\n'.join(lines)


def clean_text(text: str) -> str:
    """Очистка текста от спецсимволов и лишних пробелов"""
    # Удаляем специальные символы, оставляем только читаемые
    cleaned = re.sub(r'[^\x20-\x7Eа-яА-ЯёЁ0-9\s\.,;:\-—–№()\/\[\]{}\?!\%\$@#&\*\'\"<>\+=°C]', '', text)
    # Удаляем множественные пробелы
    cleaned = re.sub(r'\s+', ' ', cleaned)
    # Исправляем ;. на ;
    cleaned = re.sub(r';\.', ';', cleaned)
    # Исправляем ,. на ,
    cleaned = re.sub(r',\.', ',', cleaned)
    # Удаляем точку в конце если она не часть аббревиатуры
    cleaned = cleaned.rstrip('.')
    return cleaned.strip()


def extract_generic_structure(doc: Document, doc_name: str) -> str:
    """Универсальное извлечение структуры"""

    lines = []
    lines.append(f"--- Структура для документа: {doc_name}.docx ---")
    lines.append("")

    # Собираем весь текст
    full_text = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            full_text.append(text)

    if not full_text:
        return '\n'.join(lines) + "(Документ пуст)"

    # Первые 20 строк - начало документа
    lines.append("НАЧАЛО ДОКУМЕНТА:")
    for text in full_text[:15]:
        cleaned = clean_text(text)
        lines.append(f"  {cleaned}")
    lines.append("")

    # Ищем нормативные ссылки
    references = []
    for text in full_text:
        if 'ст.' in text.lower():
            refs = extract_law_references(text)
            references.extend(refs)

    if references:
        lines.append("НОРМАТИВНЫЕ ССЫЛКИ:")
        for ref in sorted(set(references)):
            lines.append(f"  - {ref}")
        lines.append("")

    # Конец документа
    lines.append("КОНЕЦ ДОКУМЕНТА:")
    for text in full_text[-5:]:
        cleaned = clean_text(text)
        lines.append(f"  {cleaned}")

    return '\n'.join(lines)


def extract_law_references(text: str) -> List[str]:
    """Извлекает ссылки на статьи законов"""
    references = []

    # Статьи: ст. 161 ЖК РФ, ст. 709 ГК РФ
    pattern = r'ст\.?\s+[\d.]+\s+[А-ЯА-я\s]+(?:Кодекс|Кодекс|РФ)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    references.extend(matches)

    # ЖК РФ, ГК РФ
    pattern2 = r'[А-Я]{2,}\s+РФ'
    matches2 = re.findall(pattern2, text)
    references.extend(matches2)

    return references


def extract_government_resolutions(text: str) -> List[str]:
    """Извлекает постановления Правительства"""
    resolutions = []

    pattern = r'Постановлен(?:ие|ия)\s+Правительств[а-я]+\s+РФ\s+от\s+[\d.]+'
    matches = re.findall(pattern, text)
    resolutions.extend(matches)

    return resolutions


def extract_main_points(text_list: List[str]) -> List[str]:
    """Извлекает основные пункты из текста"""
    points = []
    seen = set()  # Для удаления дубликатов

    for text in text_list:
        # Пропускаем короткие
        if len(text) < 50:
            continue

        # Пропускаем строковые перечисления (а), б), в), г), 1), 2), 3), -)
        if re.match(r'^\s*[а-яА-ЯёЁa-zA-Z\d]?\s*[\)\-\.]', text.strip()):
            continue

        # Ищем предложения с ключевыми словами
        if any(keyword in text.lower() for keyword in [
            'согласн', 'определен', 'должен', 'обязан', 'порядок',
            'условие', 'требован', 'разрешен', 'запрещен', 'формул',
            'норматив', 'расход', 'потреблен', 'случа', 'предусмотр',
            'осуществл', 'деятельн', 'управлен', 'контроль', 'надзор',
            'лицензи', 'реестр', 'заявлен', 'документ'
        ]):
            # Берем первое предложение полностью
            sentences = text.split('.')
            if sentences:
                first_sent = sentences[0].strip()
                # Очищаем от спецсимволов
                first_sent = clean_text(first_sent)

                # Проверяем длину и что это не обрывок
                if len(first_sent) > 60 and len(first_sent) < 300:
                    # Проверяем что не начинается с перечисления
                    if not re.match(r'^\[?[а-яА-Я]\)', first_sent):
                        # Проверяем на дубликаты
                        if first_sent not in seen:
                            points.append(first_sent)
                            seen.add(first_sent)

            if len(points) >= 25:  # Ограничиваем количество
                break

    return points


def process_directory(directory: str):
    """Обрабатывает все .docx файлы в директории"""

    dir_path = Path(directory)

    if not dir_path.exists():
        print(f"Ошибка: директория не найдена: {directory}")
        return

    # Находим все .docx файлы
    docx_files = list(dir_path.glob("*.docx"))

    if not docx_files:
        print(f"В директории {directory} нет .docx файлов")
        return

    print(f"Найдено {len(docx_files)} .docx файлов")
    print("=" * 80)

    success_count = 0
    error_count = 0

    for docx_file in docx_files:
        try:
            print(f"\nОбработка: {docx_file.name}")

            # Извлекаем структуру
            structure = extract_structure(str(docx_file))

            # Имя файла структуры
            structure_file = docx_file.with_name(f"{docx_file.stem}_structure.txt")

            # Записываем
            with open(structure_file, 'w', encoding='utf-8') as f:
                f.write(structure)

            print(f"  ✓ Создан: {structure_file.name}")
            success_count += 1

        except Exception as e:
            print(f"  ✗ Ошибка: {e}")
            error_count += 1

    print("\n" + "=" * 80)
    print(f"ГОТОВО: Обработано {success_count} файлов, ошибок {error_count}")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        directory = sys.argv[1]
    else:
        directory = "/home/olga/normativ_docs/Волков/fulldocx"

    process_directory(directory)
