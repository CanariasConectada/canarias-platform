## 19.0.1.2.0 (2026-07-10)

* Security: **Publish Homepage** now requires the *Website / Editor and
  Designer* group and write access on the company; previously any
  authenticated user could overwrite the public homepage.
* Security: the custom map URL is validated (`https://` only) to close a
  stored-XSS vector via `javascript:` / `data:` iframe sources;
  scheme-less URLs are upgraded to `https://` at render time.
* The **Corporate Microsite Look** toggle (`is_microsite_themed`) is now
  editable from *Website > Configuration > Settings*, and enabled in the
  demo website so the corporate footer is demonstrable out of the box.

## 19.0.1.0.0 (2026-07-06)

Full OCA-style rebuild of the legacy `partner_microsite_manager` (1.3.9)
for the Doodba-based architecture:

* Microsite content moved from `res.partner` to `res.company` (merchant =
  company with its own website).
* Static HTML generation replaced by a dynamic QWeb homepage template;
  the write-triggered view-rewriting sync is gone.
* Dropped: custom raw-HTML homepage toggle, logo / favicon / social link
  duplication (native per-website settings), theme footer patching,
  hardcoded attachment and website ids, `theme_corporate_multi`
  dependency, embedded `crm.lead` contact form (links to `/contactus`
  instead), "open now" JavaScript badge.
* New: explicit **Publish Homepage** action, opening-hours format
  validation as a real constraint, demo data, English source with Spanish
  translation, full test suite.
