# AGENTS.md

## Komunal-Dom Working Rules

### For UI/form changes
- Always inspect the full Django admin render stack before editing.
- Check all of: `admin.py`, `templates/admin/change_form.html`, app-level `templates/admin/...`, `static/css/admin_custom.css`, and `komunal_dom/settings.py`.
- For admin button/layout tasks, prefer one coherent global fix over scattered per-model hacks.
- Do not declare success on UI tasks without screenshot or DOM verification.

### For schema changes
- Trace every field across Django models, migrations, raw SQL, docs, admin, forms, and templates before editing.
- Prefer additive migration, data backfill, code cutover, cleanup.
- Update docs in `MD_DB/` after structural changes.

### Verification
- Python changes: restart `gunicorn-komunal-dom`.
- UI changes: verify with Playwright against real pages when credentials exist.
- Save artifacts under `tmp_archive/ui_runs/`.

### Communication
- Explain requests, plans, errors, and results in simple Russian without unnecessary jargon.
- When a technical term is unavoidable, immediately explain it in plain words.
- Prefer short, concrete wording over abstract architecture language.
