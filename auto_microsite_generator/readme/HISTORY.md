## 19.0.2.2.0 (2026-09-07)

* **The "Guía Local" dropdown belongs to the zone sites only.** 19.0.2.1.0
  had given it to every site, the portal included; the client ruled that it
  must not show on the Canarias Conectada home page, only on the commercial
  zone pages. A merchant microsite is no longer born with it, and the
  migration takes it back from the portal and from every merchant site --
  recognised by structure (the dropdown holding the three vertical URLs),
  never by label, and never on the website of a company carrying
  `zone_company_key`. The migration reads those companies straight from the
  column: a post-migration runs before `zone_company_ownership` is in the
  registry, so asking the ORM for the field there answers "no zones
  anywhere" and the sweep spares every site in silence. When the column is
  absent, or no company is keyed, the migration removes nothing and warns.

## 19.0.2.1.0 (2026-09-02)

* Every site linked the platform's own verticals (Memoria Viva, Lugares de
  Interés, Reseñas) through a "Guía Local" dropdown, and the 21 sites missing
  the `/comercio` entry got it back. Superseded for the dropdown by 19.0.2.2.0.

## 19.0.2.0.0 (2026-08-31)

Measured against website 221, the first microsite created after the cutover.
It went live missing three things every migrated site has, and all three were
generation bugs rather than data ones.

* **The subdomain is now asked for, not guessed.** Creating a company no
  longer publishes a website: it waits on the company form until somebody
  names the subdomain through the new **Create Microsite** wizard, which also
  shows the exact hostname to point DNS at. Website 221 was born on
  `neveriobradorartesanalsociedad.canariasconectada.es` because a regular
  expression chose it. New system parameter
  `auto_microsite_generator.subdomain_mode` (`ask` by default, `auto` for
  bulk imports).
* **New field** `res.company.microsite_subdomain`, validated as a DNS label
  and unique across companies, plus a computed `microsite_address`. In `auto`
  mode the derived subdomain is written back to it, so the record says where
  the site answers instead of that truth living only inside a regex; clashes
  are suffixed (`panaderia-2`) rather than raised, so a second shop of the
  same name still gets a site.
* **Menu wording is seeded in every installed language.** "Comercio" out of
  context is the noun, not the directory, and the machine translator returned
  Trade / Handel / Commerce / Commercio on website 221. The estate wording of
  Home, Shop and Directory is written on creation; `website_auto_translate`
  then refuses to overwrite it on its own (`_may_overwrite`), so no coupling
  between the two modules is needed.

## 19.0.1.1.0 (2026-07-10)

Robustness fixes from the OCA audit:

* **Fixed** `company.website_id` never refreshing after a microsite website was
  auto-generated. The core field is a stored compute without `@api.depends`, so
  the previous `invalidate_recordset` only cleared the cache without
  rescheduling the recompute; the field now stays truthy on a fresh browse.
* **Idempotent homepage**: the homepage view is only rewritten when its arch or
  key actually changed (and `is_published` only when it was `False`), so
  re-running generation no longer churns the view (write_date bumps, COW).
* **Resilient creation**: microsite generation runs inside a savepoint wrapped
  in `try/except`; a failure is logged and no longer rolls back the company
  creation.
* **Clean uninstall**: an `uninstall_hook` removes the runtime-generated
  homepage pages/views (keyed `auto_microsite_generator.homepage_*`) that are
  not tracked in `ir.model.data`, preventing a 500 after the shared template is
  dropped.
* Subdomain generation now transliterates accents
  (e.g. "Panadería Ñandú" -> "panaderianandu").

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
