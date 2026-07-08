## 19.0.1.0.0 (2026-07-08)

Full OCA-style rebuild of the legacy `auto_microsite_generator` (1.0.0) for
the Doodba-based architecture:

* Dropped the batch **microsite validator** entirely: the
  `microsite.validation.report` / `microsite.validation.line` models, their
  views, the weekly cron and the server action (the source of the 1744 junk
  validation rows) are gone.
* Made the generation **migration-aware**: content anchored to the data
  migration (`canarias_mig.*` external IDs) is detected and never
  overwritten, honouring the "COW pages as is" decision.
* Menu handling is now **create-only**: the legacy destructive cleanup
  (deleting "Memoria Viva" / "Eventos", renaming "Directorio", hardcoded
  zone subdomains) is removed.
* Dropped the `partner_microsite_manager` and `theme_corporate_multi`
  dependencies and the hand-rolled theme-view arch copying; the module now
  depends only on `website`.
* Homepage generation replaces only the blank page bootstrapped by
  `website.create`; the rich editable homepage stays with
  `partner_microsite_manager`'s explicit *Publish Homepage* action.
* New: enable/disable and domain-suffix system parameters, demo data,
  English source with Spanish translation, full test suite.
