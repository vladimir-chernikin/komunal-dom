---
name: django-admin-form-workflow
description: Use when changing Django admin forms in komunal-dom. Focus on ModelAdmin, change_form templates, Jazzmin interactions, CSS overrides, and screenshot-backed verification with Playwright when admin credentials are available.
---

# Django Admin Form Workflow

1. Identify whether the target screen is driven by `ModelAdmin.fieldsets`, a custom `change_form_template`, a global admin template override, or CSS in `static/css/admin_custom.css`.
2. Inspect all layers before editing:
 - `templates/admin/change_form.html`
 - app-specific `admin.py`
 - app-specific `templates/admin/.../change_form.html`
 - `komunal_dom/settings.py` for Jazzmin/Unfold interactions
3. Prefer the smallest global fix that satisfies the acceptance criteria across admin forms.
4. After edits, restart gunicorn if Python changed.
5. Verify with Playwright against `/admin/` using a documented test admin account when available. Capture before/after screenshots under `tmp_archive/ui_runs/`.
6. Report exact files changed and whether the result was visually verified.

Guardrails:
- Do not assume Django admin button DOM; inspect the rendered template stack first.
- If both Jazzmin and custom templates affect the screen, treat CSS and template changes as a single change set.
- For UI-only tasks, avoid touching models or migrations.
