---
name: schema-lift-fields
description: Use when moving fields between related tables in komunal-dom. Trace model, migration, admin, template, raw SQL, and reporting impact before proposing or applying schema changes.
---

# Schema Lift Fields

1. Find every occurrence of the source table and target fields in:
 - Django models
 - migrations including `RunSQL`
 - admin classes
 - forms/templates/views
 - raw SQL via `connection.cursor()` and `.sql` files
2. Produce a migration plan with:
 - schema change
 - data backfill
 - code switch-over
 - cleanup
3. Prefer additive migration first, destructive cleanup second.
4. For admin-only display moves, consider readonly proxy methods before schema edits.
5. Update DB docs after structural changes.

Never collapse child tables into parent tables without tracing raw SQL and historical migrations first.
