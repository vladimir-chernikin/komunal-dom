# WorkOrder Form Context - Quick Reference
**Generated:** 2026-03-29
**Target:** ChatGPT prompts for form modifications

---

## PROJECT
- **Root:** `/var/www/komunal-dom_ru`
- **Stack:** Django 6.0 + PostgreSQL 16 + gunicorn + nginx
- **Git:** `https://github.com/vladimir-chernikin/komunal-dom.git`
- **Branch:** `feature/tz-26-12-critical-fixes`
- **Commit:** `a24b3eba82ea3ea93dfc5279ca04aa0ec00e5a5b`
- **Language:** Russian (ru-ru)

---

## CURRENT_STATUS
- **Site:** ✅ Alive (gunicorn active)
- **Admin:** ✅ Alive (`/admin/` returns 302 → login)
- **UI Packages:**
  - `django-unfold` - INSTALLED
  - `crispy-forms` - INSTALLED
  - `crispy-bootstrap5` - INSTALLED
  - `jazzmin` - INSTALLED (legacy theme)

---

## SCREEN: WORKORDER

### URL
**Admin Detail:** `/admin/work_orders/workorder/85/change/`
- **Type:** Django Admin form (ModelAdmin)
- **Class:** `WorkOrderAdmin` (work_orders/admin.py:127)
- **Template:** Django admin default (unfold/custom)

**Custom UI:** `/work_orders/request/85/`
- **Type:** Custom template view
- **View:** `WorkOrderDetailView` (work_orders/views.py:134)
- **Template:** `work_order_detail.html`

### Screen Modes
1. **detail_full** - Admin mode (all fields, fieldsets collapsed)
2. **detail_operator** - Custom UI (truncated fields, actions)
3. **create** - Creation form (5 fields only)

---

## MAIN_FILES

### Primary Edit Target
```
/var/www/komunal-dom_ru/work_orders/admin.py
```
- **Class:** `WorkOrderAdmin` (line 127)
- **Fieldsets:** 6 groups (line 128-150)
- **List Display:** 7 columns (line 156-158)
- **Filters:** 8 filters (line 160)
- **Actions:** None (line 153)

### Related Files
```
work_orders/models.py              - DB schema (50+ fields)
work_orders/views.py               - Custom UI logic
work_orders/forms.py               - [NOT EXISTS] create if needed
work_orders/templates/work_orders/ - 8 custom templates
tmp_archive/work_order_contract_v0.2_normalized.yaml  - Full spec
```

### Key Settings
```
komunal_dom/settings.py            - INSTALLED_APPS (line 38-56)
komunal_dom/urls.py                - Admin route (line 30)
```

---

## DO_NOT_TOUCH

### Critical Zones
- ❌ **Database schema** - `models.py` field types/constraints
- ❌ **Business logic** - `views.py` permission guards
- ❌ **API endpoints** - `api_*_work_order` functions
- ❌ **Unfold integration** - Already works, don't reconfigure
- ❌ **Crispy settings** - Already configured (Bootstrap 5)

### Safe Zones
- ✅ **Admin fieldsets** - Reorder, rename, collapse
- ✅ **List display** - Add/remove columns, ordering
- ✅ **Filters** - Add/remove SimpleListFilter
- ✅ **Custom templates** - Bootstrap 5 modifications
- ✅ **Forms** - Create `forms.py` for crispy layouts

---

## QUICK_VERIFY

### After Changes
```bash
# 1. Restart gunicorn (CRITICAL for .py changes)
systemctl restart gunicorn-komunal-dom
systemctl status gunicorn-komunal-dom

# 2. Check HTTP
curl -I http://localhost:8000/admin/work_orders/workorder/85/change/

# 3. Check logs (if 500 error)
journalctl -u gunicorn-komunal-dom -n | tail -20
```

### Expected Results
- ✅ Status: `200 OK` or `302 Found` (redirect to login)
- ✅ Gunicorn: `Active: active (running)`
- ✅ No errors in journalctl

---

## KNOWN_TRAPS

### 1. Unfold Module Name
**Error:** `ModuleNotFoundError: No module named 'unfold.theme'`
**Fix:** Use only `'unfold'` in INSTALLED_APPS, NOT `'unfold.theme'`

### 2. Gunicorn Cache
**Error:** Code changes don't apply
**Fix:** ALWAYS restart gunicorn after .py file changes
**Check:** Look for new PID in `systemctl status`

### 3. mark_safe Import
**Error:** `NameError: name 'mark_safe' is not defined`
**Fix:** Import ONCE at file top: `from django.utils.safestring import mark_safe`
**Pattern:** Don't use local imports in admin methods

### 4. Admin Actions Disabled
**Code:** `actions = None` (line 153)
**Meaning:** No bulk actions, only individual form edits

### 5. Autocomplete Fields
**Usage:** `autocomplete_fields = ['company', 'service', ...]` (line 166)
**Requires:** `search_fields` in related ModelAdmin

### 6. Fieldsets Collapsed
**Pattern:** `('Служебное', {'fields': (...), 'classes': ('collapse',)})`
**Result:** Field group hidden by default (click to expand)

### 7. Readonly Fields
**Declaration:** `readonly_fields = ['created_at', 'updated_at']` (line 164)
**Override:** Can't edit even if in `fields`

### 8. Permission Filters
**Code:** `get_list_filter()` (line 199)
**Logic:** Hides filters from non-superusers unless role matches

### 9. Missing Forms
**Status:** `work_orders/forms.py` does NOT exist
**Action:** Create if using crispy-forms for custom layouts

### 10. Custom vs Admin
**Custom UI:** `/work_orders/request/<id>/` (operator view)
**Admin UI:** `/admin/work_orders/workorder/<id>/change/` (full)
**Different files:** `views.py` vs `admin.py`

---

## CHATGPT_INPUT

### Copy This Block for Prompts

```
PROJECT: Django 6.0 admin form customization
FILE: /var/www/komunal-dom_ru/work_orders/admin.py
CLASS: WorkOrderAdmin (line 127)
SCREEN: /admin/work_orders/workorder/85/change/

CURRENT FIELDSETS (6 groups):
1. Основная информация - work_order_no, company, object, service, route, department, responsible_user
2. Текущее состояние - current_internal_status, current_external_status, priority_code, is_emergency
3. Текст заявки - original_request_text, additional_info_text, resolution_text
4. Связи - request_intake, resident_user, parent_work_order
5. Жизненный цикл - 10 datetime fields (created_at, assigned_at, etc.)
6. Служебное (collapsed) - message_log_ref, completed_by_user, closed_by_user, cancelled_by_user, updated_at, is_test

CURRENT LIST DISPLAY (7 columns):
- work_order_no (clickable)
- created_at
- department
- responsible_user
- status_display (custom method)
- priority_code
- is_emergency_compact (badge)

CURRENT FILTERS (8):
- ClosedFilter (custom SimpleListFilter)
- company, department, current_internal_status, current_external_status
- priority_code, is_emergency, creation_source, is_test

CONSTRAINTS:
- Don't change models.py (DB schema)
- Don't touch business logic in views.py
- Don't reconfigure unfold/crispy (already working)
- After .py changes: systemctl restart gunicorn-komunal-dom

CONTRACT SPEC:
- Full field spec: tmp_archive/work_order_contract_v0.2_normalized.yaml
- Profiles: detail_full (admin), detail_operator (custom), create
- 50+ fields defined with importance/import rules
```

---

## REFRESH_RULE

### When to Regenerate This File
- ⚠️ **After** major admin.py refactors (fieldsets, list_display changes)
- ⚠️ **After** model schema changes (new fields, relationships)
- ⚠️ **After** Django version upgrades
- ⚠️ **After** switching from unfold to another admin theme

### No Need to Refresh
- ✅ Minor field label changes
- ✅ Template CSS modifications
- ✅ Filter additions/removals
- ✅ List display column tweaks

---

**END OF CONTEXT**
**File size:** ~120 lines (compact)
**Target:** ChatGPT prompts for WorkOrder form edits
