## 19.0.3.1.1 (2026-09-16)

* On the company form, facilities are the last section of the Microsite
  page, laid out as on the merchant's content editor (section title, then
  the catalogue as checkboxes).

## 19.0.3.1.0 (2026-09-16)

* A merchant homepage ends contact section, funding strip, footer, in that
  order (client request). The facilities block no longer hangs off
  `website.layout` above `div#footer` (the `layout_facilities` view is
  removed): there it rendered after the funding strip, between the footer
  parts. Instead a post-migration inserts
  `<t t-call="company_facilities.facilities_block"/>` right before the first
  contact section (`data-name` "Formulario" or "Formulario Contacto") of every
  imported homepage, in every language of the arch
  (`website._cf_place_facilities_in_homepage`). Homepages built from
  `microsite_homepage_content` keep the block after About; new microsites use
  that template.

## 19.0.3.0.0 (2026-09-15)

* The "Facilities and services" tab of the page-content screen is down to two
  things: the section title and the catalogue as checkboxes grouped under
  their subdivision headings, in catalogue order (`facility_checkboxes`
  widget). The "show on page" switch is gone from the screen, the company form
  and the model: the section shows exactly when the shop has ticked something.
  A pre-migration logs the shops whose page changes because of it.
* The title says what it is: "Section title", the default heading as
  placeholder, and "Leave empty to use the default heading." underneath.

## 19.0.1.0.0 (2026-08-16)

* First version: catalogue of subdivisions and items with icons, per-company
  selection, and the block on the merchant microsite.
