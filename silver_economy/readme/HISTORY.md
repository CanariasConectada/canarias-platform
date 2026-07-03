## 19.0.2.0.0

OCA-style reform. Functional fixes:

* **Coexistence with `sustainability` fixed.** Both modules extend
  `survey.user_input` with the same method names without calling `super()`,
  so only the last-loaded implementation ran: Silver surveys were being
  scored with the Sustainability thresholds (both at their defaults, which
  masked the bug) and the score-override action validated the wrong manager
  group. Shared logic now reads the per-survey parameters through the
  cooperative hook `survey.survey._get_certification_config()` and the
  shared method bodies are identical in both modules.
* Same story in QWeb: both modules replaced the same nodes of
  `survey.survey_button_retake` / `question_simple_choice` /
  `question_multiple_choice` with conditions that only knew their own flag,
  so the Retake button reappeared (and recommendations vanished) for one of
  the two survey types. The rewrites now use the shared computed flag
  `is_certification_survey` and are identical in both modules. The hard
  cross-references (`survey.is_sustainability` read from silver_economy
  templates and vice versa) are gone: each module can now be installed
  without the other.
* `UserError` was raised without being imported in `survey_survey.py`
  (crash when starting an evaluation from the backend).
* Threshold boundaries were inconsistent with the configured minimums: a
  score exactly at the "Silver minimum" (56) was awarded Bronze. A score
  equal to a level's minimum now awards that level. Existing stored levels
  are recomputed by the migration.
* The manual score override wiped itself: `action_override_score` wrote
  `scoring_total` and immediately called `_compute_scoring_values()`, which
  recomputed the score from the answer lines. The override is now persisted
  in `override_scoring_total` and reapplied by a `_compute_scoring_values`
  extension, so it survives any recomputation.
* Reminder crons spammed: they re-sent the same email every day (retry
  reminder forever once the cooldown elapsed, renewal reminder for 30 days
  straight, expiry alert forever after expiry) and the retry cron filtered
  on a hardcoded `create_date >= 2026-01-01`. Each reminder now fires
  exactly once (cooldown ends today / expiry in exactly N days / expired
  yesterday).
* Company badge fields recompute automatically through a
  `certification_input_ids` one2many with real `@api.depends`, replacing
  the manual `write`/`unlink`/`_mark_done` recompute + `flush_all`
  machinery (which missed the score-override path, leaving stale badges).
* Non-certification scored surveys no longer get a certification level
  assigned.

Cleanups: dead code removed (placeholder `has_sustain` blocks, empty
backend SCSS asset, no-op badge class map), `column_invisible` used for
context-dependent list columns, mail templates no longer hardcode "3
months" nor "/ 80 points", English source strings with a full Spanish
catalog (`i18n/es.po`), OCA manifest/readme layout, and tests for
thresholds, cooldown, override durability and company badge lifecycle.

## 19.0.1.4.1

Menu and access gated by the `group_silver_user` group; migration assigns
the group to existing internal users.
