## 19.0.2.8.3 (2026-09-15)

* A click on a row of My shops opens the page content, as the Content
  button does. The list carries a `js_class` whose controller runs the
  row's `action_microsite_content` instead of opening the website form;
  the three buttons stay.

## 19.0.2.8.2 (2026-09-15)

* "My shops" and "Page content" answered a merchant with "Error de acceso":
  Odoo 19 only runs a code action for a user who can write its model or
  belongs to one of the action's groups, and neither action named one.
  Both are now open to every internal user; the code still resolves the
  shop from the account.

## 19.0.2.8.1 (2026-09-15)

* The gate on the Dashboards root menu (`spreadsheet_dashboard`) moves to
  `merchant_group`, which now owns every menu gate of the merchant
  profile. Nothing changes for the user: the menu stays with the
  administrators.

## 19.0.2.8.0 (2026-09-15)

* **Opening hours as rows.** The merchant no longer types the compact
  notation (`L-V 09:00-14:00 / ...`, reported as "El campo horario no lo
  entiendo"): the content editor and the company form show one row per
  opening period (weekday, opens, closes, clock widget), as many per day as
  the shop needs. The text every public template reads is generated from
  the rows (`microsite.opening.slot` -> `res.company.microsite_opening_hours`,
  computed and stored) in the canonical form the parser round-trips; a
  company without rows keeps its free text. Overlapping or inverted periods
  are refused on the screen. The migration creates the rows of every
  company whose text parses and logs the ones it could not convert.
* **The hours a merchant saves now reach the page.** 210 of the 211 live
  homepages are the static pages the 2026 importer wrote, hours baked in as
  HTML; the editor wrote the company and the page never noticed ("No se
  modifican los datos en la web aunque los modifiques aquí"). The
  migration swaps that one card for a `t-call` of the new
  `microsite_opening_hours_card` template (the dynamic homepage uses the
  same one); nothing else on the page is touched. Saving the editor also
  drops the one-hour public page cache, which hid a change for logged-out
  visitors.
* The content editor and its rows are their author's only (record rules on
  `create_uid`): Odoo 19 no longer scopes transient records to their owner,
  and every merchant can write both models.

## 19.0.2.7.2 (2026-09-15)

* The hero shows the merchant's picture whole on a phone. The 60vh box
  cropped a landscape picture to a strip on narrow screens; below 768px
  the hero now takes the picture's proportion (16:9) and the picture fits
  the width, with the title and the button scaled to match. Desktop is
  unchanged. Size and padding moved from inline styles to
  `microsite_hero.scss`.

## 19.0.2.7.1 (2026-09-14)

* The microsite header follows the company logo. `website.logo` and
  `res.company.logo` are two fields; a merchant changing theirs saw the
  header keep the old one. Writing the company logo now mirrors it onto
  the company's websites. (The 120 headers that still showed a placeholder
  are repaired by data fix f51.)

## 19.0.2.7.0 (2026-09-14)

* **My shops**: an owner of several shops gets the list of their sites
  instead of the picker modal, with a button per row for the content editor,
  the site's pages and the orders placed on it. A sole owner still lands in
  the editor directly. Reported as "estamos limitando bastante por el modal".

## 19.0.2.6.2 (2026-09-14)

* **Apps** leaves the merchants' backend. The root menu ships with no groups
  and its action only needs read on `ir.module.module`, so every internal
  user was offered the platform's module list. It is now `base.group_system`,
  the same remedy already applied to Dashboards.

## 19.0.2.6.1 (2026-09-07)

* `microsite_name` is labelled **Microsite Heading**, not "Trade Name". The
  company now carries the real trade name (`comercial`, from
  `l10n_es_partner`, exposed by `res_company_zone`), and two fields labelled
  the same on one form is a question rather than a form. The field itself is
  untouched: it is still the heading the microsite prints, and the directory
  card still reads it.

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
