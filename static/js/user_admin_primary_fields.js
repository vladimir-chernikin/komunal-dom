(function () {
  function rebuildDepartmentOptions() {
    var companySelect = document.getElementById('id_primary_company');
    var departmentSelect = document.getElementById('id_primary_department');
    if (!companySelect || !departmentSelect) {
      return;
    }

    var rawMap = departmentSelect.dataset.departmentsByCompany || '{}';
    var initialValue = departmentSelect.dataset.initialValue || '';
    var selectedCompanyId = companySelect.value || '';
    var departmentsByCompany = {};

    try {
      departmentsByCompany = JSON.parse(rawMap);
    } catch (error) {
      departmentsByCompany = {};
    }

    var options = departmentsByCompany[selectedCompanyId] || [];
    var previousValue = departmentSelect.dataset.currentValue || departmentSelect.value || initialValue;

    departmentSelect.innerHTML = '';

    var emptyOption = document.createElement('option');
    emptyOption.value = '';
    emptyOption.textContent = selectedCompanyId ? '---------': 'Сначала выберите компанию';
    departmentSelect.appendChild(emptyOption);

    options.forEach(function (department) {
      var option = document.createElement('option');
      option.value = String(department.id);
      option.textContent = department.name;
      if (String(department.id) === String(previousValue)) {
        option.selected = true;
      }
      departmentSelect.appendChild(option);
    });

    if (!options.some(function (department) { return String(department.id) === String(previousValue); })) {
      departmentSelect.value = '';
    }

    departmentSelect.disabled = !selectedCompanyId;
    departmentSelect.dataset.currentValue = departmentSelect.value || '';
  }

  function initPrimaryDepartmentBinding() {
    var companySelect = document.getElementById('id_primary_company');
    var departmentSelect = document.getElementById('id_primary_department');
    if (!companySelect || !departmentSelect) {
      return;
    }

    rebuildDepartmentOptions();

    companySelect.addEventListener('change', function () {
      departmentSelect.dataset.currentValue = '';
      rebuildDepartmentOptions();
    });

    departmentSelect.addEventListener('change', function () {
      departmentSelect.dataset.currentValue = departmentSelect.value || '';
    });
  }

  window.rebuildPrimaryDepartmentOptions = rebuildDepartmentOptions;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPrimaryDepartmentBinding);
  } else {
    initPrimaryDepartmentBinding();
  }
  window.addEventListener('load', initPrimaryDepartmentBinding);
  window.setTimeout(initPrimaryDepartmentBinding, 300);
})();
