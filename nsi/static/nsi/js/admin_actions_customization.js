// Кастомизация выпадающего списка "Действия" для RefCategory
// Изменяет текст на "Быстрые действия" и добавляет tooltip

document.addEventListener('DOMContentLoaded', function() {
    // Находим все элементы label с текстом "Действия:"
    const actionLabels = document.querySelectorAll('label[for="action-select"]');

    actionLabels.forEach(function(label) {
        // Сохраняем оригинальный текст для сравнения
        if (label.textContent.trim() === 'Действия:') {
            // Меняем текст на "Быстрые действия:"
            label.textContent = 'Быстрые действия:';

            // Добавляем tooltip (title атрибут)
            label.title = 'Применяется к выбранным галочкой категориям';
            label.setAttribute('data-bs-toggle', 'tooltip');
        }
    });

    // Находим сам выпадающий список (select)
    const actionSelect = document.getElementById('action-select');

    if (actionSelect) {
        // Добавляем tooltip к select
        actionSelect.title = 'Применяется к выбранным галочкой категориям';
        actionSelect.setAttribute('data-bs-toggle', 'tooltip');
    }

    // Находим все label рядом с select (для большей совместимости)
    const allLabels = document.querySelectorAll('label');
    allLabels.forEach(function(label) {
        if (label.textContent.trim() === 'Действия:') {
            label.textContent = 'Быстрые действия:';
            label.title = 'Применяется к выбранным галочкой категориям';
        }
    });
});
