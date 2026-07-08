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
