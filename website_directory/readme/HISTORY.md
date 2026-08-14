## 19.0.7.1.0 (2026-07-09)

* **Card website URL fixed**: the entry `website_url` used to stay at the
  `website.published.mixin` placeholder (`#`) because redefining the field
  without a compute does not cancel the inherited compute. The compute is
  now overridden to read the company URL live
  (`_get_directory_website_url`: extension hook > partner website > website
  domain), so the "Visit website" button always points to the microsite.
  The company sync no longer writes the field.

## 19.0.5.0.0 (2026-07-04)

OCA-style rewrite of the module.

* **Categories**: the entry no longer holds its own M2M to the retired
  `business.category`; it exposes the company `res.company.category`
  (module `res_company_category`) as a stored related field. The public
  filter uses `child_of` on the `_parent_store` hierarchy.
* **Decoupling**: all Silver Economy / Sustainability filters were removed
  from the base module (undeclared dependencies); clean extension points
  were added for the future bridge modules. The company sync no longer
  references zone or microsite fields directly: it goes through
  overridable hooks.
* **Images**: the five hand-made resized image fields were replaced by the
  standard `image.mixin`; the public image route now streams through
  `ir.binary` (correct mimetype, ETag, cache).
* **Sync hardening**: manual SAVEPOINT/ROLLBACK SQL replaced by
  `env.cr.savepoint()`; failures are always logged; curated entry fields
  (`zone`, `short_description`, published flag) are no longer clobbered on
  update.
* **Frontend**: ~800 lines of inline JavaScript and the inline CSS moved to
  proper `web.assets_frontend` assets, rewritten without dead code and
  without production `console.log`; the dead pre-15 AMD Select2 files were
  deleted. The bespoke "searchable select" overlay was replaced by native
  selects (same behaviour, far less code).
* **Integrity**: duplicate active entries per company are now also blocked
  by a partial unique index in the database, besides the Python constraint.
