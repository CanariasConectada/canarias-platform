## 19.0.2.9.1 (2026-09-22)

- The block closing a landing page lists the *other* published seals only,
  under "Otros sellos de Canarias Conectada", and is not rendered when there
  is none. The page's own card linked the page to itself and showed its seal
  a third time; the client reported it as a duplicate.
- The body carousel plays by itself again. `website.carousel_slider` matches
  every `.carousel`; with `data-bs-interval` stripped by the sanitizer it
  created the Bootstrap instance paused, and the landing's own interaction
  got that instance back, so the Sostenibilidad page never left its first
  slide. The instance is rebuilt (and left still under
  `prefers-reduced-motion`). Accordions in a body close their other panels
  again, which `data-bs-parent` did before the sanitizer removed it.
- The 17 ODS icons sit in exactly two rows (9 + 8) from a tablet up, 6 and 5
  per row on phones, and never widen the page. Every heading of a body takes
  the accent of its vertical, whatever Bootstrap colour utility the legacy
  markup carries; the white cards of a body lose their 3rem padding on
  phones.
- Tests pin what the public page must not carry: no link into the
  questionnaire (merchants start it from *Certificaciones > Nueva
  evaluación* in the backend), and the training material listed once.
## 19.0.2.9.0 (2026-09-21)

- A merchant homepage ends facilities, certification seals, contact section,
  funding strip, footer, in that order (client request). The seals section
  hung off `website.layout` above `footer#bottom`, so it rendered after the
  funding strip. It is now a template of its own,
  `company_certification.certification_block` (takes `cc_company`, renders
  nothing for a company with no valid seal), and a post-migration inserts a
  `t-call` to it right before the first contact section (`data-name`
  "Formulario" or "Formulario Contacto") of every imported homepage, in every
  language of the arch (`website._cc_place_seals_in_homepage`). That is also
  right after the `company_facilities` call, which anchors on the same
  section; neither module depends on the other. The portal and zone websites
  (1, 12, 13, 14) are left alone; a homepage that is not well-formed XML or
  has no contact section in some language is skipped whole and logged.
- The layout-level section stays as the fallback for every other homepage
  (portal, zone websites, homepages without a contact section) and is silent
  on a page that calls the block itself (`website._cc_page_places_seals`), so
  the seals never show twice. Homepages built from
  `partner_microsite_manager.microsite_homepage_content` get the block from
  that template (`partner_microsite_manager` 19.0.2.10.0); with an older
  `partner_microsite_manager` they keep the layout-level section.
- The layout-level check reads the arch in the language being rendered, so
  a language that lost the call (builder save) falls back to the layout
  section instead of losing its seals.
- Known limit: a merchant saving the homepage in the website builder may
  flatten the `t-call` into static HTML, freezing a seal that may later
  expire. Detection hook: `website._cc_flattened_seals_homepages()` returns
  the homepages whose arch carries the rendered section (`o_cc_seals`)
  without the call; the post-migration logs them at WARNING and it can be
  run from a shell. Nothing is repaired automatically.

## 19.0.2.8.0 (2026-09-15)

- The public landing pages get their final polish. The seal gains a
  `landing_image` (Landing page tab): when set, the hero renders it as a
  full-width background behind the title, with a dark veil, served from
  `/certification/<code>/landing_image` like the badge; without it the
  gradient band stays. The hero is a 16:9 band on phones.
- One accent colour per vertical: the wrapper carries
  `data-certification-code`, and the stylesheet paints headings green for
  `sustainability` and brand blue for `silver`. The bodies no longer need
  the `sust-green` / `silver-blue` classes the retired modules served.
- The ODS icon grid, carousel captions and picture-plus-text layouts of the
  legacy bodies are styled again, scoped under the landing's rich text.
- The page closes on the platform's seals: one card per published vertical
  (the page's own included), linking to its landing page.

## 19.0.2.7.0 (2026-09-15)

- **Formación** in the Certificaciones menu now opens the online course of
  each seal (Silver Economy, Sostenibilidad) on the portal website, in the
  same tab, instead of listing downloadable material. The link is a new
  field of the seal, `training_url`, editable from the seal's Training
  Material tab; the shipped seals carry the two current course URLs and a
  post-migration fills them on an upgraded database when empty. The
  "Training material" tab of the Instrucciones screen goes with it: the
  material is still published on the seal's landing page.
- The tabs of the Instrucciones screen read "Instrucciones" and "Al
  terminar" on a Spanish backend.

## 19.0.2.6.0 (2026-09-14)

- **Instrucciones** and **Formación** in the Certificaciones menu, for seal
  holders and administrators. The instructions of each questionnaire and the
  training material were already in the database but the only backend screen
  showing them was the seal's configuration form, which is manager-only.
  Both new screens are read-only.

## 19.0.2.5.1 (2026-09-10)

- The Silver Economy and Sustainability groups move from `data/` to the
  security file. The Certificaciones menu names them and views load before
  data, so a fresh install failed with "External ID not found:
  company_certification.group_silver_user" (every doodba CI run since
  2026-09-02). Same xmlids: nothing changes on an upgraded database.

## 19.0.2.4.0 (2026-08-18)

- The per-question recommendation is now read-only guidance under the
  question instead of a comment box. `comments_allowed` used to render the
  recommendation as the placeholder of a free-comment TEXTAREA, so merchants
  thought they had to write something. The recommendation is appended to the
  question `description` as a final muted paragraph; `comments_message` is
  kept as data because the result page's improvement cards read it. The
  survey data files are `noupdate`, so a post-migration applies the same
  transform (per installed language) to the live records.
- The "Cerrar" button on the result page is wrapped like the core buttons of
  its flex row, so it no longer stretches into a misshapen oval next to
  "Volver a hacer". The retake button is now hidden for certification
  surveys at its call site: the vertical modules overwrite the `t-if`
  attribute inside `survey.survey_button_retake` (last one wins, each
  keeping only its own flag), which let the button leak back onto
  certification surveys and bypass the cooldown.

## 19.0.2.1.0 (2026-08-14)

- One list of evaluations for every seal, grouped by seal, replacing the one
  list per seal. Certificaciones > Evaluaciones now reads the way Contenido
  local reads memoria viva and lugares de interés together: a single list with
  the vertical as a group-by. Who sees which rows was already decided by
  `survey_user_input_rule_certification_user` ("a seal whose user group I
  hold, in a company I belong to"), so a merchant opens it onto their own
  seals and a manager onto every company.
- The seal modules now imply this module's per-seal groups. The two names for
  the same seal had never met, which is why the engine's rule could not fill a
  list across both.

## 19.0.1.1.0 (2026-07-23)

Closes the last gap against the legacy modules: their public landing pages
(`/silver-economy`, `/sostenibilidad`) and the training material merchants
read before taking the questionnaire.

- New `certification.material`: a titled, ordered document of one vertical,
  backed by a plain `ir.attachment` so Odoo serves it through `/web/content`
  with no controller of our own. Attaching a file publishes it, since the
  landing page is public and a private file would answer 403 to exactly the
  visitors it exists for.
- `certification.type` gains `landing_published` and `landing_description`,
  plus a **Landing Page** and a **Training Material** tab in the backend.
- New public route `/certification/<code>`, replacing the two hardcoded
  routes per vertical of the legacy modules. Unpublished or unknown verticals
  answer 404 rather than an indexable empty page.

The content stays DATA, deliberately: the legacy modules carried 12 MB of
PDFs and 1562 lines of hand-written marketing HTML inside the code. Adding a
vertical still requires zero code.

## 19.0.1.0.0 (2026-07-07)

First release. Fusion of the legacy `silver_economy` and `sustainability`
modules into one parameterizable engine:

- One `certification.type` record per vertical instead of one module per
  vertical; both legacy verticals are seeded as data (questionnaires
  included).
- Per-vertical stored fields on `res.company`
  (`silver_certification_level`, `sustain_*`, ...) replaced by generic
  `res.company.certification` status records.
- Group gating philosophy preserved from `fix/silver-sost-menu-group-gating`
  (v19.0.1.4.1): root menus and records are visible only to the vertical's
  group, never to every internal user.
- Manual override now overrides the certification level (with a full audit
  trail) instead of rewriting the computed score.
- Reminder crons now match their target date exactly instead of re-sending
  daily.

Dropped from the legacy modules (see ROADMAP for follow-ups):

- The static public pages `/silver-economy`, `/silver-economy/instructions`
  and their sustainability twins (training content and PDFs). That content
  belongs in website pages or a dedicated content module, not in code.
- The `ir.filters` presets on companies (superseded by the *Company
  Certifications* menu).
- The direct `website_directory` dependency: directory badges and filters
  live in the `website_directory_company_certification` bridge module.
