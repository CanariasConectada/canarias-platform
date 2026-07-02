## 19.0.2.0.0 (2026-07-02)

OCA-style reform:

- **Removed the dependency on `zones_company`** (retired zones cluster); the
  only coupling was a `zone_id` column in an embedded company list.
- Fixed the `post_init_hook` signature (`(cr, registry)` → `(env)`, required
  since Odoo 17): a clean install crashed before this fix.
- Removed dead code: `data/business_category_data.xml` (566 lines, not in the
  manifest), the empty `Untitled` file, the unused legacy compute field
  `res.company.business_category_id`, a never-referenced duplicate list view
  and the `unlink` override (the ORM already drops `ir.model.data` entries of
  deleted records).
- `_compute_display_name` now declares `@api.depends("complete_name")` so
  renames invalidate the cache of descendants.
- `hierarchy_level` is now the real depth (previously capped at 3).
- Source strings translated to English with an `i18n/es.po` catalog; seed
  category names stay in Spanish (business data).
- Added tests, demo data and readme fragments.

## 19.0.1.3.0 and earlier

Original module (see git history). Note: the 19.0.1.3.0 migration populated
`res_company_business_category_rel` while the field uses
`business_category_res_company_rel`, so that one-shot migration inserted into
an orphan table.
