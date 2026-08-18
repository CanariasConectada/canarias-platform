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
