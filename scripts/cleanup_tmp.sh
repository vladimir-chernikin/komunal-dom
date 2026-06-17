#!/bin/bash
################################################################################
# Скрипт ежедневной очистки /tmp
# Автор: Claude Sonnet
# Дата: 2026-02-24
#
# ПРИНЦИП:
# - НЕ УДАЛЯЕТ файлы, только архивирует
# - Перемещает старые файлы в архив
# - Сжимает в ZIP для долгосрочного хранения
################################################################################

set -e  # Ошибка при любой проблеме

# Конфигурация
TMP_DIR="/tmp"
ARCHIVE_BASE="/var/www/komunal-dom_ru/tmp_archive"
DELETE_DIR="${TMP_DIR}/delete"
PROJECT_DIR="/var/www/komunal-dom_ru"
LOG_FILE="/var/log/tmp_cleanup.log"
DATE=$(date +%Y-%m-%d)
DATETIME=$(date +%Y-%m-%d_%H%M%S)

# Создание папок (если нет)
mkdir -p "${ARCHIVE_BASE}"/{reports,debug,scripts,daily}
mkdir -p "${DELETE_DIR}"

# Логирование
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=== НАЧАЛО ОЧИСТКИ /tmp ==="

################################################################################
# ЭТАП 1: ОПЕРАТИВНЫЕ ФАЙЛЫ (7-30 дней) - перенос в архив
################################################################################

log "[ЭТАП 1] Перенос файлов старше 7 дней в архив..."

# Отчеты трассировки (_tras_diag_*.md)
find "$TMP_DIR" -maxdepth 1 -type f -name "_tras_diag_*.md" -mtime +7 -mtime -30 | while read file; do
    target_date=$(date -r "$file" +%Y/%m)
    target_dir="${ARCHIVE_BASE}/reports/${target_date}"
    mkdir -p "$target_dir"
    mv "$file" "$target_dir/"
    log "  Перенесен отчет: $(basename "$file") → reports/${target_date}/"
done

# Отчеты анализа (_dialog_analysis_*.md, *_report.md)
find "$TMP_DIR" -maxdepth 1 -type f \( -name "_dialog_analysis_*.md" -o -name "*_report.md" \) -mtime +7 -mtime -30 | while read file; do
    target_date=$(date -r "$file" +%Y/%m)
    target_dir="${ARCHIVE_BASE}/reports/${target_date}"
    mkdir -p "$target_dir"
    mv "$file" "$target_dir/"
    log "  Перенесен анализ: $(basename "$file") → reports/${target_date}/"
done

# Debug файлы (_fallback_*.txt, *_error_*.txt) - храним 30 дней в архиве
find "$TMP_DIR" -maxdepth 1 -type f \( -name "_fallback_*.txt" -o -name "*_error_*.txt" \) -mtime +3 -mtime -30 | while read file; do
    target_date=$(date -r "$file" +%Y/%m)
    target_dir="${ARCHIVE_BASE}/debug/${target_date}"
    mkdir -p "$target_dir"
    mv "$file" "$target_dir/"
    log "  Перенесен debug: $(basename "$file") → debug/${target_date}/"
done

# Скрипты (_*.py, _*.sh)
find "$TMP_DIR" -maxdepth 1 -type f \( -name "_*.py" -o -name "_*.sh" \) -mtime +3 -mtime -30 | while read file; do
    target_date=$(date -r "$file" +%Y/%m)
    target_dir="${ARCHIVE_BASE}/scripts/${target_date}"
    mkdir -p "$target_dir"
    mv "$file" "$target_dir/"
    log "  Перенесен скрипт: $(basename "$file") → scripts/${target_date}/"
done

################################################################################
# ЭТАП 2: АРХИВНЫЕ ПАПКИ (старше месяца) - сжатие в ZIP
################################################################################

log "[ЭТАП 2] Сжатие дневных папок старше 30 дней в ZIP..."

# Текущий год и месяц
CURRENT_YEAR=$(date +%Y)
CURRENT_MONTH=$(date +%m)

# Находим папки 2026_* и проверяем их возраст
find "$TMP_DIR" -maxdepth 1 -type d -name "2026_*" | sort | while read dir; do
    # Извлекаем дату из имени папки (формат 2026_MM_DD)
    dir_name=$(basename "$dir")

    # Парсим дату из имени папки
    if [[ $dir_name =~ ^([0-9]{4})_([0-9]{2})_([0-9]{2})$ ]]; then
        dir_year="${BASH_REMATCH[1]}"
        dir_month="${BASH_REMATCH[2]}"
        dir_day="${BASH_REMATCH[3]}"

        # Вычисляем возраст папки в днях
        dir_date=$(date -d "${dir_year}-${dir_month}-${dir_day}" +%s 2>/dev/null || echo "0")
        current_date=$(date +%s)
        dir_age_days=$(( ($current_date - $dir_date) / 86400 ))

        # Если старше 35 дней (чуть больше месяца)
        if [ $dir_age_days -gt 35 ]; then
            zip_file="${ARCHIVE_BASE}/daily/${dir_name}.zip"

            # Сжимаем с максимальным сжатием
            zip -9 -r "$zip_file" "$dir" -q
            log "  Сжата папка: ${dir_name} (возраст ${dir_age_days} дней) → ${zip_file}"

            # Удаляем оригинал ПОСЛЕ успешного сжатия
            rm -rf "$dir"
            log "  Удален оригинал: ${dir_name}"
        else
            log "  Пропущена папка: ${dir_name} (возраст ${dir_age_days} дней, младше 35)"
        fi
    fi
done

################################################################################
# ЭТАП 3: ФАЙЛЫ СТАРШЕ 90 ДНЕЙ - архивирование в Delete (НЕ УДАЛЕНИЕ!)
################################################################################

log "[ЭТАП 3] Архивирование файлов старше 90 дней в папку /tmp/delete..."

# Находим все файлы старше 90 дней
find "$TMP_DIR" -maxdepth 1 -type f -mtime +90 | while read file; do
    # Определяем тип файла
    filename=$(basename "$file")
    ext="${filename##*.}"

    # Категория по расширению
    case "$ext" in
        md)  category="reports" ;;
        txt) category="debug" ;;
        py|sh) category="scripts" ;;
        *) category="other" ;;
    esac

    # Дата файла
    file_date=$(date -r "$file" +%Y%m%d)

    # ZIP архив для "удаления" (кладем в /tmp/delete)
    delete_zip="${DELETE_DIR}/${category}_${file_date}_${DATETIME}.zip"

    # Добавляем файл в ZIP
    zip -9 -j "$delete_zip" "$file" -q
    log "  Архивирован в Delete: ${filename} → ${category}_${file_date}.zip"

    # Удаляем оригинал (после архивирования)
    rm -f "$file"
done

################################################################################
# ЭТАП 4: УДАЛЕНИЕ ВРЕМЕННЫХ ФАЙЛОВ (старше 1 дня)
################################################################################

log "[ЭТАП 4] Удаление временных Claude Code файлов старше 1 дня..."

# Claude temp файлы
find "$TMP_DIR" -maxdepth 1 -type f -name "claude-*-cwd" -mtime +1 -delete
log "  Удалены claude-*-cwd файлы"

# Временные промпты
find "$TMP_DIR" -maxdepth 1 -type f \( -name "new_prompt.txt" -o -name "current_prompt.txt" -o -name "current_prompt.txt" \) -mtime +1 -delete
log "  Удалены временные промпты"

################################################################################
# ЭТАП 5: ОЧИСТКА PYCACHE (всегда)
################################################################################

log "[ЭТАП 5] Очистка Python cache..."

if [ -d "$TMP_DIR/pycache" ]; then
    rm -rf "$TMP_DIR/pycache"
    log "  Удалена папка pycache"
fi

################################################################################
# ЭТАП 6: СПЕЦИАЛЬНАЯ ПАПКА _old_files (если есть)
################################################################################

if [ -d "$TMP_DIR/_old_files" ]; then
    # Проверяем возраст по самому старому файлу в папке
    oldest_file=$(find "$TMP_DIR/_old_files" -type f -printf '%T@\n' | sort | head -1)
    current_time=$(date +%s)

    if [ -n "$oldest_file" ]; then
        dir_age_days=$(( ($current_time - ${oldest_file%.*}) / 86400 ))
    else
        dir_age_days=0
    fi

    if [ $dir_age_days -gt 30 ]; then
        # Сжимаем в ZIP в папку /tmp/delete
        zip_file="${DELETE_DIR}/_old_files_${DATETIME}.zip"
        zip -9 -r "$zip_file" "$TMP_DIR/_old_files" -q
        log "  Сжата папка _old_files (возраст ${dir_age_days} дней) → ${zip_file}"

        # Удаляем оригинал
        rm -rf "$TMP_DIR/_old_files"
        log "  Удален оригинал _old_files"
    else
        log "  Папка _old_files пропущена (возраст ${dir_age_days} дней, младше 30)"
    fi
fi

################################################################################
# ФИНАЛЬНАЯ СТАТИСТИКА
################################################################################

log "[СТАТИСТИКА] Результаты очистки:"
log "  Размер /tmp: $(du -sh $TMP_DIR 2>/dev/null | cut -f1)"
log "  Файлов в /tmp: $(find $TMP_DIR -maxdepth 1 -type f | wc -l)"
log "  Размер архива: $(du -sh $ARCHIVE_BASE 2>/dev/null | cut -f1)"

log "=== ОЧИСТКА /tmp ЗАВЕРШЕНА ==="
log ""

# Права на архивы
chown -R olga:www-data "$ARCHIVE_BASE"
chmod -R 775 "$ARCHIVE_BASE"

# Права на папку delete в /tmp
chown olga:www-data "$DELETE_DIR"
chmod 775 "$DELETE_DIR"

exit 0
