/**
 * Фильтрация подразделений по компании в UserCompanyMembershipInline
 *
 * При выборе компании в поле "Компания" автоматически фильтруется
 * выпадающий список "Подразделение", показывая только подразделения
 * выбранной компании.
 */

(function($) {
    'use strict';

    // Функция для настройки фильтрации для одной строки inline
    function setupDepartmentFilter(row) {
        var companyField = row.find('input[name*="company"][name*="-lookup"]');
        var departmentField = row.find('input[name*="department"][name*="-lookup"]');
        var departmentHiddenField = row.find('input[name*="department"]:not([name*="-lookup"])');

        if (!companyField.length || !departmentField.length) {
            return;
        }

        // Обработчик изменения компании
        companyField.on('change', function() {
            var companyId = $(this).val();

            // Очищаем поле подразделения
            departmentField.val('');
            departmentHiddenField.val('');

            if (companyId) {
                // Подменяем URL autocomplete для фильтрации по компании
                var originalUrl = departmentField.attr('data-autocomplete-url');

                if (originalUrl) {
                    // Добавляем фильтр по company_id
                    var separator = originalUrl.includes('?') ? '&' : '?';
                    var filteredUrl = originalUrl + separator + 'company_id=' + companyId;
                    departmentField.attr('data-autocomplete-url', filteredUrl);
                }
            } else {
                // Сбрасываем URL на оригинальный
                var originalUrl = departmentField.attr('data-original-url') || departmentField.attr('data-autocomplete-url');
                if (originalUrl && !originalUrl.includes('company_id=')) {
                    departmentField.attr('data-autocomplete-url', originalUrl);
                }
            }
        });

        // Сохраняем оригинальный URL
        var currentUrl = departmentField.attr('data-autocomplete-url');
        if (currentUrl && !currentUrl.includes('company_id=')) {
            departmentField.attr('data-original-url', currentUrl);
        }
    }

    // Инициализация при загрузке страницы
    $(document).ready(function() {
        // Находим все inline формы
        var inlineRows = $('.dynamic-usercompanymembership_set');

        // Настраиваем фильтрацию для существующих строк
        inlineRows.each(function() {
            setupDepartmentFilter($(this));
        });

        // Настраиваем фильтрацию для новых строк при добавлении
        $(document).on('formset:added', function(event, $row) {
            if ($row.hasClass('dynamic-usercompanymembership_set')) {
                setupDepartmentFilter($row);
            }
        });
    });

})(django.jQuery);
