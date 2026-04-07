# FORM FIX CONTEXT: WorkOrder Admin
**Generated:** 2026-03-29
**Purpose:** Quick context for ChatGPT → Claude prompt generation

---

## PROJECT

**Root:** `/var/www/komunal-dom_ru`
**Stack:** Django 6.0 + PostgreSQL 16 + gunicorn + nginx + Ubuntu
**Git remote:** `https://github.com/vladimir-chernikin/komunal-dom.git`
**Branch:** `feature/tz-26-12-critical-fixes`
**Commit:** `a24b3eba82ea3ea93dfc5279ca04aa0ec00e5a5b`

---

## CURRENT_STATUS

**Site:** ✅ Alive (`http://komunal-dom.ru`)
**Admin:** ✅ Alive (`/admin/work_orders/workorder/`)
**Form stack:**
- ✅ `django-jazzmin` (primary admin theme)
- ✅ `django-crispy-forms` + `crispy-bootstrap5` (installed, configured)
- ✅ `django-unfold` (installed 0.87.0, **NOT active** - caused 502 crash)
- ✅ Standard Django admin (currently active via `admin.site`)

**Last incident:** 2026-03-29 13:07 UTC - 502 crash from unfold integration (recovered)

---

## SCREEN: WORKORDER

**URL:** `http://komunal-dom.ru/admin/work_orders/workorder/`
**Type:** Django Admin (standard, NOT unfold)
**Access:** `/admin/` → "Work Orders" → "Work Orders"
**Modes:**
1. **List view** (`changelist_view`) - table with filters
2. **Detail view** (`change_view`) - form with fieldsets
3. **Add view** (`add_view`) - creation form

**Current form:** `WorkOrderAdmin` in `work_orders/admin.py:106`
- 6 fieldsets (collapsed where noted)
- Standard Django widgets (no crispy, no unfold)
- Custom actions in `work_orders/views.py`

---

## MAIN FILES

### PRIMARY FILE TO EDIT:
```
/var/www/komunal-dom_ru/work_orders/admin.py
```
**Class:** `WorkOrderAdmin` (lines 106-151)
**What to change:** fieldsets, list_display, readonly_fields, form class

### RELATED FILES:

**Admin:**
- `work_orders/admin.py` - ALL admin classes (15 models)
- `komunal_dom/settings.py` - INSTALLED_APPS, CRISPY settings
- `komunal_dom/urls.py` - admin site routing

**Models:**
- `work_orders/models.py` - WorkOrder model (lines 550-748)

**Views (custom UI):**
- `work_orders/views.py` - API actions (take, start, complete, close)
- `work_orders/templates/work_orders/work_order_detail.html` - custom operator view

**Contract (metadata):**
- `tmp_archive/work_order_contract_v0.2_normalized.yaml` - full field spec

---

## DO NOT TOUCH

❌ **WITHOUT PERMISSION:**
- `komunal_dom/settings.py` - INSTALLED_APPS (unfold crash history)
- `komunal_dom/urls.py` - admin_site configuration (currently standard)
- `work_orders/models.py` - DB structure (migrations required)
- `work_orders/views.py` - API actions (working logic)
- `tmp_archive/*` - reference docs, NOT active code
- `.hooks/`, `.skills/`, `CLAUDE.md` - project infrastructure

⚠️ **CRITICAL:** Do NOT activate `django-unfold` without full testing in dev

---

## QUICK VERIFY

After editing `admin.py`:

```bash
# 1. Restart gunicorn
systemctl restart gunicorn-komunal-dom

# 2. Check status
systemctl status gunicorn-komunal-dom --no-pager -l | head -15

# 3. Open in browser
http://komunal-dom.ru/admin/work_orders/workorder/

# 4. Check for errors
journalctl -u gunicorn-komunal-dom -n | tail -20
```

**Expected:** Form renders, no 500 errors, fieldsets visible

---

## KNOWN_TRAPS (Top 10)

1. **Unfold crash (2026-03-29):**
   - Added `'unfold.theme'` to INSTALLED_APPS → `ModuleNotFoundError`
   - Used `UnfoldAdminSite.copy_registry()` → `AttributeError`
   - **Fix:** Only add `'unfold'` to INSTALLED_APPS, use standard `admin.site`

2. **mark_safe import error (2026-03-22):**
   - Local import in admin methods → `NameError`
   - **Fix:** Import once at file top: `from django.utils.safestring import mark_safe`

3. **Gunicorn cache (recurring):**
   - Changed .py file but old code runs
   - **Fix:** `systemctl restart gunicorn-komunal-dom`

4. **File permissions (recurring):**
   - Created files as root, nginx/gunicorn can't read
   - **Fix:** `chmod 644 file && chown olga:www-data file`

5. **Wrong DB password (2026-03-10):**
   - Used placeholder `[ПАРОЛЬ БД]` as literal
   - **Fix:** Use `~/.claude/bin/komunal_dom_db.sh` wrapper

6. **Incomplete model fields (2026-03-10):**
   - Created object without all NOT NULL fields
   - **Fix:** Check schema: `~/.claude/bin/komunal_dom_db.sh schema public.work_order`

7. **Forgot git commit (recurring):**
   - Made changes but didn't commit
   - **Fix:** `git add file && git commit` after logical step

8. **PSQL meta-commands as SQL:**
   - Used `\d table` instead of schema query
   - **Fix:** Use wrapper or `SELECT * FROM information_schema.columns...`

9. **Missing primary key in DetailView:**
   - URL pattern expects `pk_url_kwarg` but view uses wrong param
   - **Fix:** Match url kwarg with `pk_url_kwarg = 'work_order_id'`

10. **Hardcoded classifications (forbidden):**
    - Wrote if/else chains for text classification
    - **Fix:** Use LLM services or DB tags (CLAUDE.md rule)

---

## CHATGPT_INPUT

Copy this block into ChatGPT with your screenshot + requirements:

```
I need to modify a Django admin form for a WorkOrder model.

CONTEXT:
- File: /var/www/komunal-dom_ru/work_orders/admin.py (lines 106-151)
- Current: Standard Django admin with 6 fieldsets
- Stack: Django 6.0 + jazzmin theme + crispy-forms (available but not used yet)
- URL: /admin/work_orders/workorder/

CURRENT FORM STRUCTURE:
```python
@admin.register(WorkOrder)
class WorkOrderAdmin(admin.ModelAdmin):
    fieldsets = (
        ('Основная информация', {
            'fields': ('work_order_no', 'company', 'object', 'service', 'route', 'department', 'responsible_user')
        }),
        ('Текущее состояние', {
            'fields': ('current_internal_status', 'current_external_status', 'priority_code', 'is_emergency')
        }),
        ('Текст заявки', {
            'fields': ('original_request_text', 'additional_info_text', 'resolution_text')
        }),
        ('Связи', {
            'fields': ('request_intake', 'resident_user', 'parent_work_order')
        }),
        ('Жизненный цикл', {
            'fields': ('creation_source', 'created_at', 'assigned_at', 'accepted_at', 'in_progress_at',
                      'resident_contacted_at', 'localized_at', 'completed_at', 'closed_at', 'cancelled_at', 'reopened_at')
        }),
        ('Служебное', {
            'fields': ('message_log_ref', 'completed_by_user', 'closed_by_user', 'cancelled_by_user',
                      'updated_at', 'is_test'),
            'classes': ('collapse',)
        }),
    )

    list_display = ['work_order_no', 'company', 'object', 'service', 'department',
                   'responsible_user', 'current_internal_status', 'priority_code',
                   'is_emergency', 'created_at', 'is_test']

    readonly_fields = ['created_at', 'updated_at']

    autocomplete_fields = ['company', 'service', 'route', 'department',
                          'responsible_user', 'request_intake', 'resident_user',
                          'parent_work_order', 'completed_by_user', 'closed_by_user',
                          'cancelled_by_user']
```

KEY FIELDS (from contract):
- Primary identity: work_order_no, object, service
- Status: current_internal_status, current_external_status, priority_code, is_emergency
- Text: original_request_text (readonly after create), resolution_text (on complete)
- Assignment: department, responsible_user
- Lifecycle dates: created_at, assigned_at, in_progress_at, completed_at

REQUIREMENTS:
[PASTE YOUR REQUIREMENTS HERE - e.g., "hide these fields", "reorder tabs", "add inline button"]

CONSTRAINTS:
- NO django-unfold integration (caused 502 crash)
- Can use crispy-forms if needed (already installed)
- Must keep standard Django admin structure
- All FKs use autocomplete_fields (don't change to raw_select)
- Readonly fields must stay readonly
- After changes: systemctl restart gunicorn-komunal-dom

Generate:
1. Modified fieldsets structure
2. Any custom form class (if using crispy)
3. Code for admin.py (lines 106-151 replacement)
```

---

## REFRESH_RULE

**UPDATE THIS FILE WHEN:**
- New fields added to WorkOrder model
- Admin structure changed (new fieldsets, removed fields)
- Stack changes (new admin theme, new form library)
- Git commit hash changes significantly
- New incidents/traps discovered (add to top 10)

**DO NOT UPDATE FOR:**
- Minor styling tweaks (use CHATGPT_INPUT)
- One-off fixes (not structural knowledge)
- Temporary workarounds (document in separate file)

**CHECK REFRESH:**
- Run: `git rev-parse HEAD` → compare with commit above
- Run: `git branch --show-current` → compare with branch above
- If changed → regenerate this file

---

**END OF CONTEXT**
