## 19.0.7.13.0 (2026-09-07)

* **One deselect control for every filter section**: a selected zone,
  category, certification or facility is now one chip
  (`website_directory.directory_filter_chip`) that removes the filter on
  click and carries the same bold cross at its right edge, plus a visible
  focus ring. A screen reader reads out "Remove filter" and then the
  filter's own name: the words are a visually-hidden text node, not an
  aria-label, because QWeb only offers an expression attribute to the
  translator as `Remove filter: {{0}}` and it would never come back
  translated. The small "×", the category "Clear" button and the
  facilities trash icon are gone. Bridge modules call the shared template
  instead of drawing their own control.
* **One "remove" glyph per page**: the red trash of the active-filters bar
  now wears the chips' cross. It stays a red outlined button with its own
  "Clear all filters" name, because it clears every filter rather than the
  one it sits next to.

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
