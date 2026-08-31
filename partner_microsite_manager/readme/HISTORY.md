## 19.0.2.5.0 (2026-08-31)

Two blocks that all 206 migrated microsites carry hardcoded in their own
homepage were missing from the shared template, so a microsite created from
it was born without them (website 221 was):

* **Zona Comercial** — the cross-link back to the directory. Without it a new
  microsite had no way in to `/comercio` from its homepage at all. The
  heading is sentence case, not the migrated ALL CAPS: LibreTranslate returns
  `_` for shouted input.
* **Subvenciones** — the funding disclosure strip. Not decoration: the grant
  requires the emblem next to the mention of the fund on public pages, and
  209 of the 211 live sites carry it. Shipped as a module asset instead of
  pointing at the migration attachment id, which only exists in production.

## 19.0.1.3.0 (2026-07-23)

* Rescued the last visual corrections that only existed in the legacy
  `theme_corporate_multi` stylesheet (`correcciones_pt7.css`): the cookies
  bar consent buttons and the `s_company_team` certification card layout,
  in `microsite_corrections.scss`. Like the rest of the microsite look they
  are scoped to themed sites via `body:has(.o_pmm_footer)`, so the
  directory and the main website are untouched.
* This closes the migration of the legacy theme: the header phone/CTA
  hiding, the copyright bar and the footer certification badges were
  already reimplemented here, so the theme has no remaining purpose. It
  must NOT be installed alongside this module — both replace
  `//div[@id='footer']` at priority 100, they cancel each other out and the
  corporate footer silently disappears.

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
